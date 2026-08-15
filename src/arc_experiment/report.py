"""Human-readable rendering of runs and comparisons on the console."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .metrics import ConditionSummary, PairedComparison, compare, summarize
from .runner import TaskOutcome

SOLVED = "✓"
UNSOLVED = "✗"


def _mark(solved: bool) -> str:
    return SOLVED if solved else UNSOLVED


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Left-align the first column, right-align the rest, pad to content width."""
    widths: list[int] = [
        max(len(headers[i]), *(len(row[i]) for row in rows)) if rows else len(headers[i])
        for i in range(len(headers))
    ]

    def render(cells: Sequence[str]) -> str:
        parts: list[str] = [cells[0].ljust(widths[0])]
        parts.extend(cell.rjust(widths[i + 1]) for i, cell in enumerate(cells[1:]))
        return "  ".join(parts).rstrip()

    lines: list[str] = [render(headers), "  ".join("-" * width for width in widths)]
    lines.extend(render(row) for row in rows)
    return "\n".join(lines)


def progress_line(outcome: TaskOutcome, index: int, total: int) -> str:
    """One line per finished task, printed while the run is in flight."""
    counter: str = f"[{index:>3}/{total}]"
    status: str = f"{_mark(outcome.solved)} {'solved' if outcome.solved else 'failed'}"
    train: str = ""
    if outcome.iterations:
        last = outcome.iterations[-1]
        train = f"  train {last.train_correct}/{last.train_total}"
    roles: str = " ".join(f"{role[:3]}={n}" for role, n in sorted(outcome.calls_by_role.items()))
    suffix: str = f"  [{outcome.error}]" if outcome.error else ""
    return (
        f"{counter} {outcome.task_id}  {outcome.condition:<12} {status:<9}"
        f"  calls {outcome.calls_used:>2}  {roles:<16}{train}{suffix}"
    )


def summary_table(summaries: Sequence[ConditionSummary]) -> str:
    headers = (
        "Condition",
        "Tasks",
        "Solved",
        "Accuracy",
        "Train-cons.",
        "Avg calls",
        "Avg iters",
        "Leaks",
        "Errors",
    )
    rows: list[list[str]] = [
        [
            summary.condition,
            str(summary.n_tasks),
            str(summary.solved),
            f"{summary.accuracy:.1%}",
            f"{summary.train_consistency_rate:.1%}",
            f"{summary.avg_calls:.2f}",
            f"{summary.avg_iterations:.2f}",
            str(summary.leak_events),
            str(summary.api_errors),
        ]
        for summary in summaries
    ]
    return _table(headers, rows)


def comparison_block(comparison: PairedComparison) -> str:
    if comparison.n_paired == 0:
        return "No task was run under both conditions; nothing to compare."
    points: float = 100.0 * comparison.delta / comparison.n_paired
    counts: list[tuple[str, int]] = [
        ("solved by both", comparison.both_solved),
        (f"{comparison.label_a} only", comparison.only_a),
        (f"{comparison.label_b} only", comparison.only_b),
        ("solved by neither", comparison.neither),
    ]
    width: int = max(len(name) for name, _ in counts)
    lines: list[str] = [f"Paired comparison over {comparison.n_paired} task(s)"]
    lines.extend(f"  {name.ljust(width)}  {value:>4}" for name, value in counts)
    lines.append(
        f"  net gain for {comparison.label_b}: {comparison.delta:+d} task(s) ({points:+.1f} pp)"
    )
    lines.append(
        f"  exact McNemar p-value: {comparison.p_value:.4f} "
        f"(discordant pairs: {comparison.discordant})"
    )
    if comparison.excluded_api_errors:
        lines.append(
            f"  excluded from the comparison: {comparison.excluded_api_errors} task(s) "
            "whose run hit an API error"
        )
    return "\n".join(lines)


def task_table(
    records_by_condition: dict[str, list[dict[str, Any]]],
    limit: int = 60,
) -> str:
    """Per-task outcome of every condition, one column each."""
    indexed: dict[str, dict[str, dict[str, Any]]] = {
        label: {str(record["task_id"]): record for record in records}
        for label, records in records_by_condition.items()
    }
    task_ids: list[str] = sorted({task_id for column in indexed.values() for task_id in column})
    shown: list[str] = task_ids[:limit]

    def cell(record: dict[str, Any] | None) -> str:
        if record is None:
            return "-"
        mark: str = _mark(bool(record["solved"]))
        return f"{mark} {record['calls_used']}c/{len(record['iterations'])}i"

    rows: list[list[str]] = [
        [task_id] + [cell(indexed[label].get(task_id)) for label in indexed]
        for task_id in shown
    ]
    table: str = _table(["Task", *indexed], rows)
    if len(task_ids) > limit:
        table += f"\n... {len(task_ids) - limit} more task(s) omitted"
    return table


def full_report(
    records_by_condition: dict[str, list[dict[str, Any]]],
    show_tasks: bool = True,
) -> str:
    """Complete console report: per-task table, summaries and paired comparison."""
    blocks: list[str] = []
    labels: list[str] = [label for label, records in records_by_condition.items() if records]
    if not labels:
        return "No results recorded."

    if show_tasks:
        blocks.append(task_table({label: records_by_condition[label] for label in labels}))

    blocks.append(
        summary_table([summarize(records_by_condition[label], label) for label in labels])
    )

    if len(labels) == 2:
        blocks.append(
            comparison_block(
                compare(
                    records_by_condition[labels[0]],
                    records_by_condition[labels[1]],
                    labels[0],
                    labels[1],
                )
            )
        )
    return "\n\n".join(blocks)
