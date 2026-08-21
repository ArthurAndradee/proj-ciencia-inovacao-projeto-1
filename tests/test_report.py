from typing import Any

from arc_experiment import report
from arc_experiment.metrics import PairedComparison, summarize
from arc_experiment.runner import IterationRecord, TaskOutcome


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
        "input_tokens": 0,
        "output_tokens": 0,
        "error": None,
    }


def outcome(solved: bool, error: str | None = None) -> TaskOutcome:
    return TaskOutcome(
        task_id="007bbfb7",
        condition="critic",
        solved=solved,
        train_consistent=solved,
        calls_used=5,
        calls_by_role={"generator": 3, "critic": 2},
        iterations=[
            IterationRecord(
                index=1,
                rule="r",
                code="c",
                executed=True,
                exec_error=None,
                train_correct=2,
                train_total=3,
            )
        ],
        final_code="c",
        final_rule="r",
        stop_reason="budget_exhausted",
        leak_events=0,
        input_tokens=0,
        output_tokens=0,
        error=error,
    )


def test_progress_line_shows_identity_and_budget() -> None:
    line: str = report.progress_line(outcome(solved=True), index=3, total=20)
    assert "[  3/20]" in line
    assert "007bbfb7" in line and "critic" in line
    assert report.SOLVED in line and "solved" in line
    assert "calls  5" in line and "gen=3" in line and "cri=2" in line
    assert "train 2/3" in line


def test_progress_line_reports_failure_and_api_error() -> None:
    line: str = report.progress_line(outcome(solved=False, error="429"), index=1, total=1)
    assert report.UNSOLVED in line and "failed" in line
    assert "[429]" in line


def test_summary_table_has_one_row_per_condition() -> None:
    table: str = report.summary_table(
        [
            summarize([record("a", "sampling", True), record("b", "sampling", False)]),
            summarize([record("a", "critic", True), record("b", "critic", True)]),
        ]
    )
    lines: list[str] = table.splitlines()
    assert lines[0].startswith("Condition")
    assert len(lines) == 4  # header, separator, two conditions
    assert "50.0%" in lines[2] and "100.0%" in lines[3]


def test_comparison_block_reports_the_contingency_and_p_value() -> None:
    block: str = report.comparison_block(
        PairedComparison(
            n_paired=10,
            both_solved=3,
            only_a=1,
            only_b=4,
            neither=2,
            p_value=0.375,
            label_a="sampling",
            label_b="critic",
        )
    )
    assert "over 10 task(s)" in block
    assert "sampling only" in block and "critic only" in block
    assert "+3 task(s) (+30.0 pp)" in block
    assert "0.3750" in block


def test_comparison_block_flags_excluded_api_errors() -> None:
    block: str = report.comparison_block(
        PairedComparison(
            n_paired=8,
            both_solved=3,
            only_a=1,
            only_b=2,
            neither=2,
            p_value=1.0,
            label_a="sampling",
            label_b="critic",
            excluded_api_errors=2,
        )
    )
    assert "excluded from the comparison: 2 task(s)" in block


def test_comparison_block_without_paired_tasks() -> None:
    empty = PairedComparison(0, 0, 0, 0, 0, 1.0)
    assert "nothing to compare" in report.comparison_block(empty)


def test_task_table_adapts_to_the_number_of_conditions() -> None:
    single: str = report.task_table({"sampling": [record("a", "sampling", True)]})
    assert single.splitlines()[0].split() == ["Task", "sampling"]

    paired: str = report.task_table(
        {
            "sampling": [record("a", "sampling", True)],
            "critic": [record("a", "critic", False)],
        }
    )
    assert paired.splitlines()[0].split() == ["Task", "sampling", "critic"]
    assert "4c/4i" in paired


def test_task_table_marks_missing_results() -> None:
    table: str = report.task_table(
        {"sampling": [record("a", "sampling", True)], "critic": []}
    )
    assert table.splitlines()[-1].endswith("-")


def test_task_table_truncates_long_runs() -> None:
    many = [record(f"t{i:03d}", "sampling", i % 2 == 0) for i in range(70)]
    table: str = report.task_table({"sampling": many}, limit=10)
    assert "60 more task(s) omitted" in table


def test_full_report_includes_comparison_only_for_two_conditions() -> None:
    both: str = report.full_report(
        {
            "sampling": [record("a", "sampling", True)],
            "critic": [record("a", "critic", False)],
        }
    )
    assert "Paired comparison" in both

    single: str = report.full_report({"sampling": [record("a", "sampling", True)]})
    assert "Paired comparison" not in single


def test_full_report_without_records() -> None:
    assert report.full_report({"sampling": [], "critic": []}) == "No results recorded."


def test_progress_line_shows_the_candidate_that_was_tested() -> None:
    """Regression: a solved task printed `train 0/3` from the last iteration.

    Selection is by train_correct, so the best iteration is the one whose code
    ran against the test pair. Printing the last one contradicted `solved`.
    """

    def record(index: int, correct: int) -> IterationRecord:
        return IterationRecord(
            index=index, rule="r", code="c", executed=True, exec_error=None,
            train_correct=correct, train_total=3,
        )

    solved = outcome(solved=True)
    solved.iterations = [record(1, 0), record(2, 0), record(3, 1), record(4, 0)]

    line: str = report.progress_line(solved, index=52, total=172)
    assert "train 1/3" in line  # the selected candidate, not the last
    assert "solved" in line
