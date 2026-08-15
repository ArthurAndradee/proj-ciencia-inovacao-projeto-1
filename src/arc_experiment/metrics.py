"""Aggregation of outcomes and the paired significance test between conditions."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from math import comb
from pathlib import Path
from typing import Any

from .runner import TaskOutcome


def load_outcomes(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def as_records(outcomes: Sequence[TaskOutcome]) -> list[dict[str, Any]]:
    return [outcome.to_dict() for outcome in outcomes]


@dataclass(frozen=True)
class ConditionSummary:
    """Descriptive statistics of one condition over a set of tasks."""

    condition: str
    n_tasks: int
    solved: int
    train_consistent: int
    total_calls: int
    total_iterations: int
    leak_events: int
    input_tokens: int
    output_tokens: int
    api_errors: int

    @property
    def accuracy(self) -> float:
        return self.solved / self.n_tasks if self.n_tasks else 0.0

    @property
    def train_consistency_rate(self) -> float:
        return self.train_consistent / self.n_tasks if self.n_tasks else 0.0

    @property
    def avg_calls(self) -> float:
        return self.total_calls / self.n_tasks if self.n_tasks else 0.0

    @property
    def avg_iterations(self) -> float:
        return self.total_iterations / self.n_tasks if self.n_tasks else 0.0


def summarize(records: Sequence[dict[str, Any]], condition: str = "") -> ConditionSummary:
    return ConditionSummary(
        condition=condition or (str(records[0]["condition"]) if records else ""),
        n_tasks=len(records),
        solved=sum(1 for r in records if r["solved"]),
        train_consistent=sum(1 for r in records if r["train_consistent"]),
        total_calls=sum(int(r["calls_used"]) for r in records),
        total_iterations=sum(len(r["iterations"]) for r in records),
        leak_events=sum(int(r["leak_events"]) for r in records),
        input_tokens=sum(int(r["input_tokens"]) for r in records),
        output_tokens=sum(int(r["output_tokens"]) for r in records),
        api_errors=sum(1 for r in records if r.get("error")),
    )


@dataclass(frozen=True)
class PairedComparison:
    """McNemar contingency between two conditions over the same tasks."""

    n_paired: int
    both_solved: int
    only_a: int
    only_b: int
    neither: int
    p_value: float
    label_a: str = "a"
    label_b: str = "b"
    excluded_api_errors: int = 0

    @property
    def discordant(self) -> int:
        return self.only_a + self.only_b

    @property
    def delta(self) -> int:
        """Net tasks gained by condition B over condition A."""
        return self.only_b - self.only_a


def exact_mcnemar_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value (binomial sign test on discordant pairs)."""
    n: int = only_a + only_b
    if n == 0:
        return 1.0
    smaller: int = min(only_a, only_b)
    tail: float = sum(comb(n, k) for k in range(smaller + 1)) / (2**n)
    return min(1.0, 2 * tail)


def compare(
    records_a: Sequence[dict[str, Any]],
    records_b: Sequence[dict[str, Any]],
    label_a: str = "baseline",
    label_b: str = "intervention",
) -> PairedComparison:
    """Compare two conditions over the tasks both of them actually ran.

    Tasks whose run hit an API error in either condition are dropped: an
    unavailable model is not evidence about the method, and counting it as a
    failure would hand the other condition a discordant pair it did not earn.
    """
    solved_a: dict[str, bool] = {str(r["task_id"]): bool(r["solved"]) for r in records_a}
    solved_b: dict[str, bool] = {str(r["task_id"]): bool(r["solved"]) for r in records_b}
    failed_calls: set[str] = {
        str(record["task_id"])
        for record in (*records_a, *records_b)
        if record.get("error")
    }
    shared_all: set[str] = set(solved_a) & set(solved_b)
    shared: list[str] = sorted(shared_all - failed_calls)
    excluded: int = len(shared_all & failed_calls)

    both: int = sum(1 for t in shared if solved_a[t] and solved_b[t])
    only_a: int = sum(1 for t in shared if solved_a[t] and not solved_b[t])
    only_b: int = sum(1 for t in shared if solved_b[t] and not solved_a[t])
    neither: int = len(shared) - both - only_a - only_b

    return PairedComparison(
        n_paired=len(shared),
        both_solved=both,
        only_a=only_a,
        only_b=only_b,
        neither=neither,
        p_value=exact_mcnemar_p(only_a, only_b),
        label_a=label_a,
        label_b=label_b,
        excluded_api_errors=excluded,
    )
