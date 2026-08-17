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
