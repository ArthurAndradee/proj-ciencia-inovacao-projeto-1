from typing import Any

import pytest

from arc_experiment.metrics import ConditionSummary, compare, exact_mcnemar_p, summarize


def record(task_id: str, condition: str, solved: bool, calls: int = 4) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "condition": condition,
        "solved": solved,
        "train_consistent": solved,
        "calls_used": calls,
        "calls_by_role": {"generator": calls},
        "iterations": [{}] * calls,
        "leak_events": 0,
        "input_tokens": 100,
        "output_tokens": 50,
        "error": None,
    }


def test_summarize_computes_rates() -> None:
    records = [record("a", "baseline", True), record("b", "baseline", False)]
    summary: ConditionSummary = summarize(records)
    assert summary.condition == "baseline"
    assert summary.n_tasks == 2 and summary.solved == 1
    assert summary.accuracy == 0.5
    assert summary.avg_calls == 4.0
    assert summary.input_tokens == 200


def test_summarize_empty() -> None:
    summary: ConditionSummary = summarize([], condition="baseline")
    assert summary.n_tasks == 0 and summary.accuracy == 0.0


def test_compare_builds_the_contingency_table() -> None:
    baseline = [record(t, "baseline", s) for t, s in [("a", True), ("b", True), ("c", False)]]
    intervention = [
        record(t, "intervention", s) for t, s in [("a", True), ("b", False), ("c", True)]
    ]
    result = compare(baseline, intervention)
    assert result.n_paired == 3
    assert (result.both_solved, result.only_a, result.only_b, result.neither) == (1, 1, 1, 0)
    assert result.delta == 0
    assert result.discordant == 2


def test_compare_uses_only_shared_tasks() -> None:
    baseline = [record("a", "baseline", True), record("b", "baseline", True)]
    intervention = [record("a", "intervention", False)]
    result = compare(baseline, intervention)
    assert result.n_paired == 1 and result.only_a == 1


def test_mcnemar_without_discordant_pairs() -> None:
    assert exact_mcnemar_p(0, 0) == 1.0


def test_mcnemar_is_symmetric_and_bounded() -> None:
    assert exact_mcnemar_p(3, 7) == exact_mcnemar_p(7, 3)
    assert 0.0 <= exact_mcnemar_p(1, 9) <= 1.0


def test_mcnemar_known_values() -> None:
    # All discordant pairs favour one side: p = 2 * 0.5^n
    assert exact_mcnemar_p(0, 5) == pytest.approx(2 * 0.5**5)
    # Balanced discordance is maximally non-significant.
    assert exact_mcnemar_p(5, 5) == 1.0


def test_mcnemar_detects_a_strong_effect() -> None:
    assert exact_mcnemar_p(1, 12) < 0.01
