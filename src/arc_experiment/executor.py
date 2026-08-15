"""Isolated execution of the candidate code produced by the LLM."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import grids
from .dataset import Grid, Pair

CHILD: Path = Path(__file__).with_name("_sandbox_child.py")

_FENCE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text: str) -> str | None:
    """Extract the last fenced block that defines transform()."""
    blocks: list[str] = [block.strip() for block in _FENCE.findall(text)]
    for block in reversed(blocks):
        if "def transform" in block:
            return block
    if "def transform" in text:
        return text.strip()
    return None


@dataclass(frozen=True)
class CaseResult:
    """Outcome of running the candidate on a single pair."""

    ok: bool
    got: Grid | None
    error: str | None
    correct: bool
    diff: str


@dataclass(frozen=True)
class RunResult:
    ok: bool
    error: str | None
    cases: list[CaseResult]

    @property
    def all_correct(self) -> bool:
        return self.ok and bool(self.cases) and all(case.correct for case in self.cases)

    @property
    def n_correct(self) -> int:
        return sum(1 for case in self.cases if case.correct)


def _resource_limits(memory_mb: int) -> Callable[[], None]:
    """Build a preexec_fn applying CPU/memory limits to the child (POSIX only)."""

    def apply() -> None:
        import resource

        soft_memory: int = memory_mb * 1024 * 1024
        for name in ("RLIMIT_AS", "RLIMIT_DATA"):
            limit: int | None = getattr(resource, name, None)
            if limit is None:
                continue
            try:
                resource.setrlimit(limit, (soft_memory, soft_memory))
            except (ValueError, OSError):
                pass
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
        except (ValueError, OSError, AttributeError):
            pass

    return apply


def run_code(
    code: str,
    pairs: Sequence[Pair],
    timeout_s: float = 10.0,
    memory_mb: int = 1024,
) -> RunResult:
    """Run transform() over the inputs of `pairs` and compare with expected outputs."""
    with tempfile.TemporaryDirectory(prefix="arc-exec-") as tmp:
        code_path: Path = Path(tmp) / "candidate.py"
        code_path.write_text(code)
        payload: str = json.dumps([pair.input for pair in pairs])
        try:
            process = subprocess.run(
                [sys.executable, "-I", str(CHILD), str(code_path)],
                input=payload,
                capture_output=True,
                text=True,
                timeout=timeout_s,
                cwd=tmp,
                preexec_fn=_resource_limits(memory_mb) if sys.platform != "win32" else None,
            )
        except subprocess.TimeoutExpired:
            return RunResult(ok=False, error=f"timed out after {timeout_s:.0f}s", cases=[])

    if process.returncode != 0:
        stderr_tail: list[str] = (process.stderr or "").strip().splitlines()[-1:]
        detail: str = stderr_tail[0] if stderr_tail else "process terminated"
        return RunResult(ok=False, error=f"execution failed: {detail}", cases=[])

    try:
        data: dict[str, Any] = json.loads(process.stdout)
    except json.JSONDecodeError:
        return RunResult(ok=False, error="unreadable child process output", cases=[])

    if not data["ok"]:
        return RunResult(ok=False, error=str(data["error"]), cases=[])

    cases: list[CaseResult] = []
    for pair, item in zip(pairs, data["outputs"]):
        got: Grid | None = item["grid"] if item["ok"] else None
        correct: bool = grids.equal(pair.output, got)
        diff: str = item["error"] if not item["ok"] else grids.diff_summary(pair.output, got)
        cases.append(
            CaseResult(ok=bool(item["ok"]), got=got, error=item["error"], correct=correct, diff=diff)
        )
    return RunResult(ok=True, error=None, cases=cases)
