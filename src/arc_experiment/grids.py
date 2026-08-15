"""Serialization and comparison of ARC grids."""

from __future__ import annotations

from .dataset import Grid


def render(grid: Grid) -> str:
    """Render a grid as text: dimensions on the first line, then the digits."""
    rows: int = len(grid)
    cols: int = len(grid[0]) if rows else 0
    body: str = "\n".join(" ".join(str(cell) for cell in row) for row in grid)
    return f"{rows}x{cols}\n{body}"


def equal(a: Grid | None, b: Grid | None) -> bool:
    return a is not None and b is not None and a == b


def shape(grid: Grid) -> tuple[int, int]:
    """Rows and columns of a non-empty grid."""
    return len(grid), len(grid[0]) if grid else 0


def diff_summary(expected: Grid, got: Grid | None) -> str:
    """Describe how `got` diverges from `expected`.

    Used for the baseline's execution feedback, where the expected grids are
    training pairs the generator already sees, and as an internal input to the
    critic (whose own output is leak-filtered before reaching the generator).
    """
    if got is None:
        return "the function did not return a valid grid"

    expected_shape: tuple[int, int] = shape(expected)
    got_shape: tuple[int, int] = shape(got)
    if expected_shape != got_shape:
        return (
            f"shape mismatch: expected {expected_shape[0]}x{expected_shape[1]}, "
            f"got {got_shape[0]}x{got_shape[1]}"
        )

    wrong: list[tuple[int, int, int, int]] = [
        (row, col, expected[row][col], got[row][col])
        for row in range(expected_shape[0])
        for col in range(expected_shape[1])
        if expected[row][col] != got[row][col]
    ]
    if not wrong:
        return "output matches"

    total: int = expected_shape[0] * expected_shape[1]
    sample: str = "; ".join(
        f"({row},{col}) expected {exp} got {obtained}" for row, col, exp, obtained in wrong[:12]
    )
    ellipsis: str = " ..." if len(wrong) > 12 else ""
    return f"{len(wrong)}/{total} cells differ: {sample}{ellipsis}"
