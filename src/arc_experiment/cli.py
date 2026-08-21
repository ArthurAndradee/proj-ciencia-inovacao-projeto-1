"""Command-line interface.

    uv run arc-exp run --task 007bbfb7 --mode both
    uv run arc-exp run --sample 20 --mode both
    uv run arc-exp report --run-id evaluation-n20-seed20260814-b12
    uv run arc-exp tasks --sample 5
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import report
from .config import Config
from .dataset import Task, find_task, sample_tasks
from .experiment import pending_work, run_experiment, run_id_for
from .keypool import PooledClient
from .llm import LLMClient, ScriptedClient
from .metrics import load_outcomes
from .ratelimit import PermanentAPIError, QuotaExhausted
from .runner import Condition, TaskOutcome

MODES: dict[str, tuple[Condition, ...]] = {
    "sampling": (Condition.SAMPLING,),
    "critic": (Condition.CRITIC,),
    "both": (Condition.SAMPLING, Condition.CRITIC),
}

DRY_RUN_ANSWER: str = (
    "## RULE\nDry run: the grid is returned unchanged.\n"
    "## CODE\n```python\ndef transform(grid):\n    return grid\n```"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arc-exp",
        description="ARC-AGI-1: is it better to diversify or to iterate?",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="run tasks under one or both conditions")
    selection = run.add_mutually_exclusive_group()
    selection.add_argument(
        "--task", action="append", metavar="ID", help="task id (repeatable)"
    )
    selection.add_argument("--sample", type=int, metavar="N", help="draw N random tasks")
    selection.add_argument(
        "--tasks-file",
        type=Path,
        metavar="PATH",
        help="file with one task id per line (blank lines and # comments ignored)",
    )
    run.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="both",
        help="sampling = best-of-N only, critic = oracle critic only, "
        "both = the paired comparison",
    )
    run.add_argument("--split", choices=("training", "evaluation"))
    run.add_argument("--seed", type=int)
    run.add_argument("--budget", type=int, metavar="N", help="API calls per task")
    run.add_argument(
        "--rpm",
        type=int,
        metavar="N",
        help="throttle to N requests per minute PER KEY (0 disables; use your "
        "free-tier cap, which applies to each key separately)",
    )
    run.add_argument("--generator-model")
    run.add_argument("--critic-model")
    run.add_argument(
        "--sampling-temperature",
        type=float,
        metavar="T",
        help="temperature of the sampling condition (diversity is its whole point)",
    )
    run.add_argument(
        "--workers",
        type=int,
        default=None,
        metavar="N",
        help="run N tasks concurrently (default: one per API key, since each key "
        "carries its own quota and its own per-minute cap)",
    )
    run.add_argument("--run-id", help="override the results directory name")
    run.add_argument(
        "--fresh", action="store_true", help="discard previous results for this run id"
    )
    run.add_argument(
        "--dry-run",
        action="store_true",
        help="use a canned answer instead of the API (no key, no cost)",
    )
    run.add_argument("--quiet", action="store_true", help="only print the final report")

    report_cmd = subparsers.add_parser("report", help="re-render a finished run")
    target = report_cmd.add_mutually_exclusive_group(required=True)
    target.add_argument("--run-id")
    target.add_argument("--run-dir", type=Path)
    report_cmd.add_argument("--no-tasks", action="store_true", help="hide the per-task table")

    tasks_cmd = subparsers.add_parser("tasks", help="list the task ids a seed selects")
    tasks_cmd.add_argument("--sample", type=int, default=10, metavar="N")
    tasks_cmd.add_argument("--split", choices=("training", "evaluation"))
    tasks_cmd.add_argument("--seed", type=int)

    return parser


def config_from_args(args: argparse.Namespace) -> Config:
    """Environment configuration with the CLI overrides applied on top."""
    config: Config = Config.from_env()
    overrides: dict[str, Any] = {}
    for attribute, field_name in (
        ("split", "split"),
        ("seed", "seed"),
        ("budget", "budget_calls"),
        ("sample", "sample_size"),
        ("generator_model", "generator_model"),
        ("critic_model", "critic_model"),
        ("rpm", "rpm"),
        ("sampling_temperature", "sampling_temperature"),
    ):
        value = getattr(args, attribute, None)
        if value is not None:
            overrides[field_name] = value
    return dataclasses.replace(config, **overrides) if overrides else config


def read_task_ids(path: Path) -> list[str]:
    """Task ids from a file, one per line; blank lines and # comments ignored."""
    ids: list[str] = []
    for line in path.read_text().splitlines():
        stripped: str = line.split("#", 1)[0].strip()
        if stripped:
            ids.append(stripped)
    if not ids:
        raise ValueError(f"no task ids in {path}")
    return ids


def resolve_tasks(args: argparse.Namespace, config: Config) -> list[Task]:
    explicit: list[str] = list(getattr(args, "task", None) or [])
    tasks_file: Path | None = getattr(args, "tasks_file", None)
    if tasks_file is not None:
        explicit = read_task_ids(tasks_file)
    if explicit:
        return [find_task(config.data_dir, task_id, config.split) for task_id in explicit]
    return sample_tasks(config.data_dir, config.split, config.sample_size, config.seed)


POOLED_RETRIES: int = 3


def make_client(config: Config, dry_run: bool) -> LLMClient:
    if dry_run:
        return ScriptedClient(default=DRY_RUN_ANSWER)
    return PooledClient.from_keys(
        api_keys=config.api_keys,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        # With more than one key, failing over beats insisting: another key is a
        # different quota, while another retry is the same one a moment later.
        max_retries=config.max_retries if len(config.api_keys) == 1 else POOLED_RETRIES,
        rpm=config.rpm,
        timeout_s=config.request_timeout_s,
    )


def default_run_id(args: argparse.Namespace, config: Config, tasks: Sequence[Task]) -> str:
    """Explicit task lists get their own directory, keyed by the ids themselves."""
    if not getattr(args, "task", None) and getattr(args, "tasks_file", None) is None:
        return run_id_for(config)
    head: str = tasks[0].task_id
    suffix: str = f"+{len(tasks) - 1}" if len(tasks) > 1 else ""
    return f"task-{head}{suffix}-b{config.budget_calls}"


def pacing_note(runs: int, config: Config) -> str:
    """Floor on the wall time the throttle imposes — never the estimate.

    Model latency adds on top and can dominate: at 1.9s/call the throttle
    rules, at 92.8s/call it is irrelevant and this floor understates the run
    fiftyfold. Reporting it as a total once promised 47 minutes for a job of
    31 hours.

    The throttle is per key, so N keys divide the floor by N — counting it once
    for the whole run would overstate the wait by exactly the factor the extra
    keys were added to gain.
    """
    keys: int = max(len(config.api_keys), 1)
    seconds_per_call: float = 60.0 / config.rpm
    floor_minutes: float = seconds_per_call * config.budget_calls * runs / 60.0 / keys
    return (
        f"Throttled to {config.rpm} rpm per key: {seconds_per_call:.0f}s between "
        f"calls on each of {keys} key(s), so at least ~{floor_minutes:.0f} min — "
        "model latency adds on top. A line is printed as each task finishes."
    )


def resolve_workers(args: argparse.Namespace, config: Config) -> int:
    """One worker per key by default: each key has its own quota and own throttle."""
    if args.workers is not None:
        requested: int = int(args.workers)
        return max(requested, 1)
    if args.dry_run:
        return 1
    return max(len(config.api_keys), 1)


def command_run(args: argparse.Namespace) -> int:
    config: Config = config_from_args(args)
    conditions: tuple[Condition, ...] = MODES[args.mode]
    if not args.dry_run and not config.api_keys:
        print(
            "no API keys. Set GOOGLE_API_KEYS (comma-separated) or GOOGLE_API_KEY "
            "in .env, or pass --dry-run.",
            file=sys.stderr,
        )
        return 1
    tasks: list[Task] = resolve_tasks(args, config)
    run_id: str = args.run_id or default_run_id(args, config, tasks)
    run_dir: Path = config.results_dir / "runs" / run_id

    if args.fresh:
        for condition in conditions:
            (run_dir / f"{condition.value}.jsonl").unlink(missing_ok=True)

    # What this invocation will actually run: on a resume the finished tasks
    # are skipped, so counting them would make a complete run end short.
    total: int = pending_work(run_dir, tasks, conditions)
    workers: int = resolve_workers(args, config)
    state: dict[str, int] = {"done": 0}

    def on_progress(outcome: TaskOutcome) -> None:
        state["done"] += 1
        if not args.quiet:
            print(report.progress_line(outcome, state["done"], total), flush=True)

    if not args.quiet:
        models: str = config.generator_model + (
            f" / {config.critic_model}"
            if Condition.CRITIC in conditions
            and config.critic_model != config.generator_model
            else ""
        )
        print(
            f"Running {len(tasks)} task(s) x {len(conditions)} condition(s) "
            f"| split={config.split} seed={config.seed} budget={config.budget_calls} "
            f"| model={models}" + ("  [DRY RUN]" if args.dry_run else ""),
            flush=True,
        )
        if workers > 1:
            print(
                f"Running {workers} tasks concurrently across "
                f"{len(config.api_keys)} API key(s).",
                flush=True,
            )
        if config.rpm > 0 and not args.dry_run:
            # Output only appears when a task finishes, and a throttled task can
            # take a minute. Say so, so the wait does not look like a hang.
            print(pacing_note(total, config), flush=True)

    client: LLMClient = make_client(config, args.dry_run)
    exit_code: int = 0
    try:
        run_experiment(
            config=config,
            client=client,
            conditions=conditions,
            tasks=tasks,
            run_id=run_id,
            on_progress=on_progress,
            workers=workers,
        )
    except QuotaExhausted as exc:
        print(f"\nDaily quota exhausted: {exc}", file=sys.stderr)
        print(
            "Results so far are saved. Re-run the same command once the quota "
            "resets to continue from where it stopped.",
            file=sys.stderr,
        )
        exit_code = 2
    except PermanentAPIError as exc:
        print(f"\nAPI rejected the request: {exc}", file=sys.stderr)
        exit_code = 1
    except KeyboardInterrupt:
        # Tasks are written as they finish, so the interrupted one is the only
        # loss. Re-running the same command picks up from the last saved task.
        print("\nInterrupted. Finished tasks are saved; re-run to continue.", file=sys.stderr)
        exit_code = 130

    print()
    if isinstance(client, PooledClient):
        print(key_usage_table(client, run_dir))
    print(render_run(run_dir, conditions))
    print(f"\nResults: {run_dir}")
    return exit_code


def key_usage_table(client: PooledClient, run_dir: Path) -> str:
    """What each key contributed, and which ones ran dry.

    Written to disk as well: when a run stops early, the next one needs to know
    whether it was the quota that ended it or something else.
    """
    usage: list[dict[str, Any]] = client.usage()
    (run_dir / "keys.json").write_text(json.dumps(usage, indent=2) + "\n")
    lines: list[str] = ["API keys"]
    for entry in usage:
        spent: str = (
            "  REJECTED by the API (dropped from the pool)"
            if entry.get("rejected")
            else f"  spent: {', '.join(entry['exhausted'])}"
            if entry["exhausted"]
            else ""
        )
        failures: str = f"  {entry['failures']} failure(s)" if entry["failures"] else ""
        lines.append(f"  {entry['key']}: {entry['calls']} call(s){failures}{spent}")
    return "\n".join(lines)


def render_run(
    run_dir: Path,
    conditions: Sequence[Condition] = tuple(Condition),
    show_tasks: bool = True,
) -> str:
    records = {
        condition.value: load_outcomes(run_dir / f"{condition.value}.jsonl")
        for condition in conditions
    }
    return report.full_report(records, show_tasks=show_tasks)


def command_report(args: argparse.Namespace) -> int:
    config: Config = Config.from_env()
    run_dir: Path = args.run_dir or config.results_dir / "runs" / args.run_id
    if not run_dir.is_dir():
        print(f"run directory not found: {run_dir}", file=sys.stderr)
        return 1
    print(render_run(run_dir, show_tasks=not args.no_tasks))
    print(f"\nResults: {run_dir}")
    return 0


def command_tasks(args: argparse.Namespace) -> int:
    config: Config = config_from_args(args)
    tasks: list[Task] = sample_tasks(
        config.data_dir, config.split, config.sample_size, config.seed
    )
    print(f"{len(tasks)} task(s) | split={config.split} seed={config.seed}")
    for task in tasks:
        print(
            f"  {task.task_id}  train={len(task.train)} pair(s)  "
            f"test={len(task.test)} pair(s)"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args: argparse.Namespace = build_parser().parse_args(argv)
    commands = {"run": command_run, "report": command_report, "tasks": command_tasks}
    return commands[str(args.command)](args)


if __name__ == "__main__":
    raise SystemExit(main())
