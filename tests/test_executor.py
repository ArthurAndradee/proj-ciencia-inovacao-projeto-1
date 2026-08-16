from arc_experiment.dataset import Pair
from arc_experiment.executor import RunResult, extract_code, run_code

IDENTITY: str = "def transform(grid):\n    return grid\n"


def test_extract_code_takes_fenced_block() -> None:
    text: str = "reasoning\n```python\ndef transform(grid):\n    return grid\n```\nend"
    assert extract_code(text) == "def transform(grid):\n    return grid"


def test_extract_code_prefers_last_block_with_transform() -> None:
    text: str = "```python\nx = 1\n```\n```python\ndef transform(g):\n    return g\n```"
    code: str | None = extract_code(text)
    assert code is not None and "def transform" in code


def test_extract_code_without_function_returns_none() -> None:
    assert extract_code("```python\nprint(1)\n```") is None


def test_correct_execution() -> None:
    result: RunResult = run_code(IDENTITY, [Pair([[1, 2]], [[1, 2]])])
    assert result.all_correct and result.n_correct == 1


def test_incorrect_execution_produces_diff() -> None:
    result: RunResult = run_code(IDENTITY, [Pair([[1, 2]], [[3, 4]])])
    assert result.ok and not result.all_correct
    assert "cells differ" in result.cases[0].diff


def test_runtime_error_does_not_crash_the_parent() -> None:
    result: RunResult = run_code(
        "def transform(grid):\n    raise ValueError('boom')\n", [Pair([[1]], [[1]])]
    )
    assert result.ok and not result.cases[0].ok
    assert "ValueError" in result.cases[0].diff


def test_syntax_error() -> None:
    result: RunResult = run_code("def transform(:\n", [Pair([[1]], [[1]])])
    assert not result.ok and result.error is not None and "SyntaxError" in result.error


def test_missing_function() -> None:
    result: RunResult = run_code("def other(grid):\n    return grid\n", [Pair([[1]], [[1]])])
    assert not result.ok and result.error is not None and "transform" in result.error


def test_invalid_return_becomes_null_grid() -> None:
    result: RunResult = run_code("def transform(grid):\n    return 42\n", [Pair([[1]], [[1]])])
    assert result.ok and result.cases[0].got is None


def test_timeout() -> None:
    result: RunResult = run_code(
        "def transform(grid):\n    while True:\n        pass\n",
        [Pair([[1]], [[1]])],
        timeout_s=2,
    )
    assert not result.ok and result.error is not None and "timed out" in result.error


def test_mutating_the_input_does_not_affect_comparison() -> None:
    code: str = "def transform(grid):\n    grid[0][0] = 9\n    return [[7]]\n"
    result: RunResult = run_code(code, [Pair([[1]], [[7]])])
    assert result.all_correct
