from arc_experiment.guards import REDACTION, Sanitized, sanitize


def test_plain_feedback_passes_through() -> None:
    text: str = "Your rule assumes the shape is preserved, but it is not in example 2."
    result: Sanitized = sanitize(text)
    assert result.text == text
    assert not result.leaked


def test_redacts_grid_rows() -> None:
    result: Sanitized = sanitize("The target is:\n0 7 7\n7 7 7\nas you can see")
    assert REDACTION in result.text
    assert "0 7 7" not in result.text and "7 7 7" not in result.text
    assert result.violations.count("grid_row") == 2


def test_redacts_comma_separated_rows() -> None:
    result: Sanitized = sanitize("[1, 2, 3]")
    assert result.leaked


def test_redacts_code_fences() -> None:
    result: Sanitized = sanitize("try this\n```python\ndef transform(g):\n    return g\n```\n")
    assert "def transform" not in result.text
    assert "code_fence" in result.violations


def test_redacts_bare_code_lines() -> None:
    result: Sanitized = sanitize("do this:\nimport numpy as np\nreturn grid[::-1]")
    assert "import numpy" not in result.text
    assert result.violations.count("code_line") == 2


def test_prose_with_a_single_number_is_kept() -> None:
    text: str = "Example 3 has 4 distinct colours, which your rule ignores."
    assert sanitize(text).text == text


def test_narrow_grids_slip_past_the_row_guard() -> None:
    """Known hole, pinned deliberately: `_GRID_ROW` needs three or more values.

    A 2-wide grid row is indistinguishable from ordinary prose containing two
    numbers, so the guard lets it through. In the evaluation split 9 of 400
    tasks have a test target this narrow (6 of the 270 in the official run), and
    for those the critic's prose was never actually filtered. Widening the
    pattern would also redact sentences like "examples 2 3", so the trade is
    left as it is and recorded here rather than discovered again later.
    """
    assert not sanitize("2 4").leaked
    assert sanitize("2 4 6").leaked


def test_the_injected_block_would_not_survive_the_guard() -> None:
    """Why the injection arms bypass `sanitize` instead of going through it.

    The disclosure the ceiling arm depends on is exactly what this guard exists
    to destroy. Routing it through here would silently empty those arms, so the
    runner appends the block after sanitizing — and this test pins the reason.
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, "src")
    from arc_experiment import prompts
    from arc_experiment.dataset import Pair, Task
    from arc_experiment.executor import run_code

    task = Task(
        task_id="triple",
        train=[Pair([[1, 2, 3]], [[2, 4, 6]])],
        test=[Pair([[5, 5, 5]], [[10, 10, 10]])],
    )
    result = run_code("def transform(grid):\n    return grid\n", task.train)
    block: str = prompts.counterexample_block(task, result, include_test=True)

    assert "2 4 6" in block and "10 10 10" in block
    guarded: Sanitized = sanitize(block)
    assert guarded.leaked
    assert "10 10 10" not in guarded.text
