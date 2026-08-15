"""Run orchestration: task iteration, result persistence and resumability."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import prompts
from .config import Config
from .dataset import Task, sample_tasks
from .llm import LLMClient
from .runner import Condition, TaskOutcome, solve_task

ProgressCallback = Callable[[TaskOutcome], None]


def run_id_for(config: Config) -> str:
    """Deterministic run identifier: same configuration, same directory."""
    return f"{config.split}-n{config.sample_size}-seed{config.seed}-b{config.budget_calls}"


def _git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


def _prompt_digest() -> dict[str, str]:
    """Hash of the system prompts, so a run cannot be silently re-interpreted."""
    return {
        name: hashlib.sha256(text.encode()).hexdigest()[:16]
        for name, text in (
            ("generator_system", prompts.GENERATOR_SYSTEM),
            ("critic_system", prompts.CRITIC_SYSTEM),
        )
    }


def write_manifest(run_dir: Path, config: Config, tasks: Sequence[Task]) -> Path:
    manifest: dict[str, Any] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "git_commit": _git_commit(),
        "python": sys.version.split()[0],
        "config": config.manifest(),
        "prompt_digest": _prompt_digest(),
        "task_ids": [task.task_id for task in tasks],
    }
    path: Path = run_dir / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2) + "\n")
    return path


def completed_task_ids(path: Path) -> set[str]:
    """Task ids already recorded, so an interrupted run can be resumed."""
    if not path.exists():
        return set()
    done: set[str] = set()
    for line in path.read_text().splitlines():
        if line.strip():
            done.add(str(json.loads(line)["task_id"]))
    return done


def append_outcome(path: Path, outcome: TaskOutcome) -> None:
    with path.open("a") as handle:
        handle.write(json.dumps(outcome.to_dict(), ensure_ascii=False) + "\n")
        handle.flush()


def run_experiment(
    config: Config,
    client: LLMClient,
    conditions: Iterable[Condition] = (Condition.BASELINE, Condition.INTERVENTION),
    tasks: Sequence[Task] | None = None,
    run_id: str | None = None,
    on_progress: ProgressCallback | None = None,
) -> Path:
    """Run every task under every condition, writing one JSONL file per condition.

    Results are appended as each task finishes and already-recorded tasks are
    skipped, so a crashed or rate-limited run can be restarted without paying
    for the work already done.
    """
    selected: Sequence[Task] = (
        tasks
        if tasks is not None
        else sample_tasks(config.data_dir, config.split, config.sample_size, config.seed)
    )
    run_dir: Path = config.results_dir / "runs" / (run_id or run_id_for(config))
    run_dir.mkdir(parents=True, exist_ok=True)
    write_manifest(run_dir, config, selected)

    for condition in conditions:
        path: Path = run_dir / f"{condition.value}.jsonl"
        done: set[str] = completed_task_ids(path)
        for task in selected:
            if task.task_id in done:
                continue
            outcome: TaskOutcome = solve_task(
                task=task,
                condition=condition,
                client=client,
                generator_model=config.generator_model,
                critic_model=config.critic_model,
                budget_calls=config.budget_calls,
                exec_timeout_s=config.exec_timeout_s,
                exec_memory_mb=config.exec_memory_mb,
            )
            append_outcome(path, outcome)
            if on_progress is not None:
                on_progress(outcome)

    return run_dir
