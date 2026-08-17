from pathlib import Path

from arc_experiment.config import REPO_ROOT
from arc_experiment.dataset import Task, load_split, load_task, sample_tasks

DATA: Path = REPO_ROOT / "data"


def test_loads_task() -> None:
    task: Task = load_task(DATA / "training" / "007bbfb7.json")
    assert task.task_id == "007bbfb7"
    assert len(task.train) == 5
    assert task.test_pair.input and task.test_pair.output


def test_each_split_has_400_tasks() -> None:
    assert len(load_split(DATA, "training")) == 400
    assert len(load_split(DATA, "evaluation")) == 400


def test_sampling_is_deterministic() -> None:
    first: list[str] = [t.task_id for t in sample_tasks(DATA, "evaluation", 10, seed=42)]
    again: list[str] = [t.task_id for t in sample_tasks(DATA, "evaluation", 10, seed=42)]
    other: list[str] = [t.task_id for t in sample_tasks(DATA, "evaluation", 10, seed=7)]
    assert first == again
    assert first != other
    assert first == sorted(first)


def test_sample_larger_than_split_returns_everything() -> None:
    assert len(sample_tasks(DATA, "training", 10_000, seed=1)) == 400
