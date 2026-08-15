import json
from pathlib import Path
from typing import Any

from arc_experiment.config import Config
from arc_experiment.dataset import Pair, Task
from arc_experiment.experiment import (
    completed_task_ids,
    run_experiment,
    run_id_for,
    write_manifest,
)
from arc_experiment.llm import ScriptedClient
from arc_experiment.runner import Condition

CORRECT: str = (
    "## RULE\nDouble every cell.\n## CODE\n```python\ndef transform(grid):\n"
    "    return [[c * 2 for c in row] for row in grid]\n```"
)

TASKS: list[Task] = [
    Task(task_id="t1", train=[Pair([[1]], [[2]])], test=[Pair([[3]], [[6]])]),
    Task(task_id="t2", train=[Pair([[2]], [[4]])], test=[Pair([[5]], [[10]])]),
]


def make_config(tmp_path: Path) -> Config:
    return Config(
        api_key="",
        generator_model="gen",
        critic_model="crit",
        split="evaluation",
        sample_size=2,
        seed=1,
        budget_calls=4,
        temperature=0.0,
        max_output_tokens=256,
        rpm=0,
        max_retries=3,
        exec_timeout_s=10.0,
        exec_memory_mb=512,
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
    )


def test_run_id_is_deterministic(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert run_id_for(config) == "evaluation-n2-seed1-b4"


def test_run_writes_one_file_per_condition(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run_dir: Path = run_experiment(
        config, ScriptedClient(default=CORRECT), tasks=TASKS
    )
    for condition in Condition:
        records = [
            json.loads(line)
            for line in (run_dir / f"{condition.value}.jsonl").read_text().splitlines()
        ]
        assert [r["task_id"] for r in records] == ["t1", "t2"]
        assert all(r["solved"] for r in records)


def test_manifest_records_config_without_the_api_key(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run_dir: Path = config.results_dir / "runs" / "manual"
    run_dir.mkdir(parents=True)
    manifest: dict[str, Any] = json.loads(write_manifest(run_dir, config, TASKS).read_text())
    assert "api_key" not in manifest["config"]
    assert manifest["task_ids"] == ["t1", "t2"]
    assert set(manifest["prompt_digest"]) == {"generator_system", "critic_system"}


def test_completed_tasks_are_skipped_on_resume(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first_client = ScriptedClient(default=CORRECT)
    run_dir: Path = run_experiment(
        config, first_client, conditions=[Condition.BASELINE], tasks=TASKS
    )
    calls_after_first_run: int = len(first_client.calls)

    second_client = ScriptedClient(default=CORRECT)
    run_experiment(config, second_client, conditions=[Condition.BASELINE], tasks=TASKS)

    assert calls_after_first_run == 2
    assert second_client.calls == []  # nothing re-run, nothing re-paid
    assert completed_task_ids(run_dir / "baseline.jsonl") == {"t1", "t2"}


def test_progress_callback_receives_each_outcome(tmp_path: Path) -> None:
    seen: list[str] = []
    run_experiment(
        make_config(tmp_path),
        ScriptedClient(default=CORRECT),
        conditions=[Condition.INTERVENTION],
        tasks=TASKS,
        on_progress=lambda outcome: seen.append(outcome.task_id),
    )
    assert seen == ["t1", "t2"]
