"""Loading and sampling of ARC-AGI-1 tasks."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

Grid = list[list[int]]


@dataclass(frozen=True)
class Pair:
    """One input/output demonstration of a task."""

    input: Grid
    output: Grid


@dataclass(frozen=True)
class Task:
    task_id: str
    train: list[Pair]
    test: list[Pair]

    @property
    def test_pair(self) -> Pair:
        """The evaluated test pair. Tasks with several pairs use the first one."""
        return self.test[0]


def _pairs(raw: list[dict[str, Grid]]) -> list[Pair]:
    return [Pair(input=item["input"], output=item["output"]) for item in raw]


def load_task(path: Path) -> Task:
    raw: dict[str, Any] = json.loads(path.read_text())
    return Task(task_id=path.stem, train=_pairs(raw["train"]), test=_pairs(raw["test"]))


def load_split(data_dir: Path, split: str) -> list[Task]:
    split_dir: Path = data_dir / split
    if not split_dir.is_dir():
        raise FileNotFoundError(f"split not found: {split_dir}")
    return [load_task(path) for path in sorted(split_dir.glob("*.json"))]


def find_task(data_dir: Path, task_id: str, split: str | None = None) -> Task:
    """Look a task up by id, trying `split` first and then the remaining splits."""
    ordered: list[str] = [split] if split else []
    ordered += [name for name in ("training", "evaluation") if name != split]
    for candidate in ordered:
        path: Path = data_dir / candidate / f"{task_id}.json"
        if path.is_file():
            return load_task(path)
    raise FileNotFoundError(f"task {task_id!r} not found under {data_dir}")


def sample_tasks(data_dir: Path, split: str, size: int, seed: int) -> list[Task]:
    """Deterministic sample: the same seed and split always yield the same tasks."""
    tasks: list[Task] = load_split(data_dir, split)
    if size <= 0 or size >= len(tasks):
        return tasks
    rng = random.Random(seed)
    chosen: list[Task] = rng.sample(sorted(tasks, key=lambda task: task.task_id), size)
    return sorted(chosen, key=lambda task: task.task_id)
