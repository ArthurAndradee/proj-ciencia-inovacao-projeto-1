from arc_experiment import grids


def test_render_includes_dimensions() -> None:
    assert grids.render([[0, 1], [2, 3]]) == "2x2\n0 1\n2 3"


def test_equal() -> None:
    assert grids.equal([[1]], [[1]])
    assert not grids.equal([[1]], [[2]])
    assert not grids.equal([[1]], None)


def test_diff_reports_shape_mismatch() -> None:
    summary: str = grids.diff_summary([[1, 1]], [[1], [1]])
    assert "shape mismatch" in summary
    assert "1x2" in summary and "2x1" in summary


def test_diff_reports_cells() -> None:
    summary: str = grids.diff_summary([[1, 2], [3, 4]], [[1, 2], [3, 9]])
    assert "1/4 cells differ" in summary
    assert "(1,1) expected 4 got 9" in summary


def test_diff_without_divergence() -> None:
    assert grids.diff_summary([[1]], [[1]]) == "output matches"


def test_diff_invalid_grid() -> None:
    assert "did not return a valid grid" in grids.diff_summary([[1]], None)
