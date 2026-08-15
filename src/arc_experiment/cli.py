"""Command-line interface.

    uv run arc-exp run --task 007bbfb7 --mode both
    uv run arc-exp run --sample 20 --mode both
    uv run arc-exp report --run-id evaluation-n20-seed20260814-b12
    uv run arc-exp tasks --sample 5
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from . import report
from .config import Config
from .dataset import Task, find_task, sample_tasks
from .experiment import run_experiment, run_id_for
from .llm import GeminiClient, LLMClient, ScriptedClient
from .metrics import load_outcomes
from .ratelimit import PermanentAPIError, QuotaExhausted
from .runner import Condition, TaskOutcome

MODES: dict[str, tuple[Condition, ...]] = {
    "single": (Condition.BASELINE,),
    "feedback": (Condition.INTERVENTION,),
    "both": (Condition.BASELINE, Condition.INTERVENTION),
}

DRY_RUN_ANSWER: str = (
    "## RULE\nDry run: the grid is returned unchanged.\n"
    "## CODE\n```python\ndef transform(grid):\n    return grid\n```"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="arc-exp",
        description="ARC-AGI-1: self-debugging baseline vs. oracle-critic intervention.",
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
    run.add_argument(
        "--mode",
        choices=sorted(MODES),
        default="both",
        help="single = baseline only, feedback = critic only, both = paired comparison",
    )
    run.add_argument("--split", choices=("training", "evaluation"))
    run.add_argument("--seed", type=int)
    run.add_argument("--budget", type=int, metavar="N", help="API calls per task")
    run.add_argument(
        "--rpm",
        type=int,
        metavar="N",
        help="throttle to N requests per minute (0 disables; use your free-tier cap)",
    )
    run.add_argument("--generator-model")
    run.add_argument("--critic-model")
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
    ):
        value = getattr(args, attribute, None)
        if value is not None:
            overrides[field_name] = value
    return dataclasses.replace(config, **overrides) if overrides else config


def resolve_tasks(args: argparse.Namespace, config: Config) -> list[Task]:
    if getattr(args, "task", None):
        return [find_task(config.data_dir, task_id, config.split) for task_id in args.task]
    return sample_tasks(config.data_dir, config.split, config.sample_size, config.seed)


def make_client(config: Config, dry_run: bool) -> LLMClient:
    if dry_run:
        return ScriptedClient(default=DRY_RUN_ANSWER)
    return GeminiClient(
        api_key=config.api_key,
        temperature=config.temperature,
        max_output_tokens=config.max_output_tokens,
        max_retries=config.max_retries,
        rpm=config.rpm,
    )


def default_run_id(args: argparse.Namespace, config: Config, tasks: Sequence[Task]) -> str:
    """Explicit task lists get their own directory, keyed by the ids themselves."""
    if not getattr(args, "task", None):
        return run_id_for(config)
    head: str = tasks[0].task_id
    suffix: str = f"+{len(tasks) - 1}" if len(tasks) > 1 else ""
    return f"task-{head}{suffix}-b{config.budget_calls}"


def command_run(args: argparse.Namespace) -> int:
    config: Config = config_from_args(args)
    conditions: tuple[Condition, ...] = MODES[args.mode]
    tasks: list[Task] = resolve_tasks(args, config)
    run_id: str = args.run_id or default_run_id(args, config, tasks)
    run_dir: Path = config.results_dir / "runs" / run_id

    if args.fresh:
        for condition in conditions:
            (run_dir / f"{condition.value}.jsonl").unlink(missing_ok=True)

    total: int = len(tasks) * len(conditions)
    state: dict[str, int] = {"done": 0}

    def on_progress(outcome: TaskOutcome) -> None:
        state["done"] += 1
        if not args.quiet:
            print(report.progress_line(outcome, state["done"], total), flush=True)

    if not args.quiet:
        models: str = config.generator_model + (
            f" / {config.critic_model}"
            if Condition.INTERVENTION in conditions
            and config.critic_model != config.generator_model
            else ""
        )
        print(
            f"Running {len(tasks)} task(s) x {len(conditions)} condition(s) "
            f"| split={config.split} seed={config.seed} budget={config.budget_calls} "
            f"| model={models}" + ("  [DRY RUN]" if args.dry_run else ""),
            flush=True,
        )

    exit_code: int = 0
    try:
        run_experiment(
            config=config,
            client=make_client(config, args.dry_run),
            conditions=conditions,
            tasks=tasks,
            run_id=run_id,
            on_progress=on_progress,
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

    print()
    print(render_run(run_dir, conditions))
    print(f"\nResults: {run_dir}")
    return exit_code


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
