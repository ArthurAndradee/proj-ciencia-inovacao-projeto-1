"""Child process that runs LLM-generated candidate code.

Reads the code path from argv[1] and the list of input grids as JSON on stdin.
Writes to stdout a JSON object {"ok": bool, "outputs": [...], "error": str | null}.
It must never be imported by the parent process.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def normalize(value: Any) -> list[list[int]] | None:
    """Accept lists, tuples and objects exposing .tolist(); reject anything else."""
    if hasattr(value, "tolist"):
        value = value.tolist()
    if not isinstance(value, (list, tuple)) or not value:
        return None
    grid: list[list[int]] = []
    for row in value:
        if hasattr(row, "tolist"):
            row = row.tolist()
        if not isinstance(row, (list, tuple)) or not row:
            return None
        try:
            grid.append([int(cell) for cell in row])
        except (TypeError, ValueError):
            return None
    if len({len(row) for row in grid}) != 1:
        return None
    return grid


def main() -> None:
    code_path: str = sys.argv[1]
    inputs: list[list[list[int]]] = json.load(sys.stdin)

    namespace: dict[str, Any] = {"__name__": "__arc_candidate__"}
    try:
        with open(code_path, encoding="utf-8") as handle:
            source: str = handle.read()
        exec(compile(source, "<candidate>", "exec"), namespace)
    except BaseException as exc:  # syntax, import or module-level failure
        print(json.dumps({"ok": False, "outputs": [], "error": f"{type(exc).__name__}: {exc}"}))
        return

    transform: Any = namespace.get("transform")
    if not callable(transform):
        print(json.dumps({"ok": False, "outputs": [], "error": "transform() is not defined"}))
        return

    outputs: list[dict[str, Any]] = []
    for grid in inputs:
        try:
            result: Any = transform([row[:] for row in grid])
        except BaseException as exc:
            outputs.append(
                {"ok": False, "grid": None, "error": f"{type(exc).__name__}: {exc}"}
            )
            continue
        outputs.append({"ok": True, "grid": normalize(result), "error": None})

    print(json.dumps({"ok": True, "outputs": outputs, "error": None}))


if __name__ == "__main__":
    main()
