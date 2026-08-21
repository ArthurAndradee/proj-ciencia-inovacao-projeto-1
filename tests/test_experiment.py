import json
import threading
from pathlib import Path
from typing import Any

from arc_experiment.config import Config
from arc_experiment.dataset import Pair, Task
from arc_experiment.experiment import (
    completed_task_ids,
    run_experiment,
    run_id_for,
    write_manifest,
)
from arc_experiment.llm import ScriptedClient
from arc_experiment.runner import Condition, TaskOutcome

# The conditions `run_experiment` pairs by default.
PAIRED: tuple[Condition, ...] = (Condition.SAMPLING, Condition.CRITIC)

CORRECT: str = (
    "## RULE\nDouble every cell.\n## CODE\n```python\ndef transform(grid):\n"
    "    return [[c * 2 for c in row] for row in grid]\n```"
)

TASKS: list[Task] = [
    Task(task_id="t1", train=[Pair([[1]], [[2]])], test=[Pair([[3]], [[6]])]),
    Task(task_id="t2", train=[Pair([[2]], [[4]])], test=[Pair([[5]], [[10]])]),
]


def make_config(tmp_path: Path) -> Config:
    return Config(
        api_keys=("k1", "k2"),
        generator_model="gen",
        critic_model="crit",
        split="evaluation",
        sample_size=2,
        seed=1,
        budget_calls=4,
        temperature=0.0,
        sampling_temperature=0.8,
        max_output_tokens=256,
        rpm=0,
        max_retries=3,
        request_timeout_s=180.0,
        exec_timeout_s=10.0,
        exec_memory_mb=512,
        data_dir=tmp_path / "data",
        results_dir=tmp_path / "results",
    )


def test_run_id_is_deterministic(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    assert run_id_for(config) == "evaluation-n2-seed1-b4"


def test_run_writes_one_file_per_condition(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run_dir: Path = run_experiment(
        config, ScriptedClient(default=CORRECT), tasks=TASKS
    )
    for condition in PAIRED:
        records = [
            json.loads(line)
            for line in (run_dir / f"{condition.value}.jsonl").read_text().splitlines()
        ]
        assert [r["task_id"] for r in records] == ["t1", "t2"]
        assert all(r["solved"] for r in records)


def test_each_condition_runs_at_its_own_temperature(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    client = ScriptedClient(default=CORRECT)
    run_experiment(
        config,
        client,
        conditions=list(PAIRED),
        tasks=TASKS[:1],
    )
    assert [call.temperature for call in client.calls] == [0.8, 0.0]


def test_conditions_are_interleaved_so_an_abort_leaves_whole_pairs(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []
    run_experiment(
        make_config(tmp_path),
        ScriptedClient(default=CORRECT),
        conditions=list(PAIRED),
        tasks=TASKS,
        on_progress=lambda o: seen.append((o.task_id, o.condition)),
    )
    # Task-major: t1 finishes under both conditions before t2 starts. Running
    # condition-major would leave every task of one and none of the other when
    # a quota cuts the run short, which the paired comparison cannot use.
    assert seen == [
        ("t1", "sampling"), ("t1", "critic"),
        ("t2", "sampling"), ("t2", "critic"),
    ]


MANY: list[Task] = [
    Task(task_id=f"t{i:02d}", train=[Pair([[i]], [[i * 2]])], test=[Pair([[1]], [[2]])])
    for i in range(12)
]


def test_workers_keep_each_task_pair_together(tmp_path: Path) -> None:
    seen: list[tuple[str, str]] = []
    lock = threading.Lock()

    def note(outcome: TaskOutcome) -> None:
        with lock:
            seen.append((outcome.task_id, outcome.condition))

    run_experiment(
        make_config(tmp_path),
        ScriptedClient(default=CORRECT),
        conditions=list(PAIRED),
        tasks=MANY,
        on_progress=note,
        workers=4,
    )
    assert len(seen) == 2 * len(MANY)
    # Order across tasks is now nondeterministic, but a task never appears
    # under one condition without the other: that is what keeps an interrupted
    # run usable by the paired comparison.
    by_task: dict[str, set[str]] = {}
    for task_id, condition in seen:
        by_task.setdefault(task_id, set()).add(condition)
    assert all(v == {"sampling", "critic"} for v in by_task.values())


def test_workers_record_every_task_exactly_once(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run_dir: Path = run_experiment(
        config,
        ScriptedClient(default=CORRECT),
        conditions=list(PAIRED),
        tasks=MANY,
        workers=4,
    )
    for condition in PAIRED:
        ids = [
            json.loads(line)["task_id"]
            for line in (run_dir / f"{condition.value}.jsonl").read_text().splitlines()
        ]
        assert sorted(ids) == sorted(task.task_id for task in MANY)
        assert len(ids) == len(set(ids))  # concurrent appends never duplicated


def test_manifest_records_the_key_count_but_never_the_keys(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    run_dir: Path = config.results_dir / "runs" / "manual"
    run_dir.mkdir(parents=True)
    manifest: dict[str, Any] = json.loads(write_manifest(run_dir, config, TASKS).read_text())
    assert "api_keys" not in manifest["config"]
    assert "k1" not in manifest["config"].values()
    # How many quotas the run could draw on explains its pace and where it stopped.
    assert manifest["config"]["key_count"] == 2
    assert manifest["task_ids"] == ["t1", "t2"]
    assert set(manifest["prompt_digest"]) == {"generator_system", "critic_system"}


def test_completed_tasks_are_skipped_on_resume(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    first_client = ScriptedClient(default=CORRECT)
    run_dir: Path = run_experiment(
        config, first_client, conditions=[Condition.SAMPLING], tasks=TASKS
    )
    calls_after_first_run: int = len(first_client.calls)

    second_client = ScriptedClient(default=CORRECT)
    run_experiment(config, second_client, conditions=[Condition.SAMPLING], tasks=TASKS)

    assert calls_after_first_run == 2
    assert second_client.calls == []  # nothing re-run, nothing re-paid
    assert completed_task_ids(run_dir / "sampling.jsonl") == {"t1", "t2"}


def test_progress_callback_receives_each_outcome(tmp_path: Path) -> None:
    seen: list[str] = []
    run_experiment(
        make_config(tmp_path),
        ScriptedClient(default=CORRECT),
        conditions=[Condition.CRITIC],
        tasks=TASKS,
        on_progress=lambda outcome: seen.append(outcome.task_id),
    )
    assert seen == ["t1", "t2"]


def test_a_key_running_dry_mid_run_does_not_end_the_run(tmp_path: Path) -> None:
    """The scenario the pool exists for: one quota dies, the run carries on.

    A single-key run raises `QuotaExhausted` out of the first spent call and
    loses every task still in flight. With a pool, the dead key steps aside and
    the remaining keys finish the work.
    """
    from arc_experiment.keypool import PooledClient
    from arc_experiment.llm import Completion, Message
    from arc_experiment.ratelimit import QuotaExhausted

    class DyingKey:
        """Answers `budget` times, then reports its daily quota gone, forever."""

        def __init__(self, budget: int) -> None:
            self.budget: int = budget
            self.lock = threading.Lock()

        def generate(
            self,
            model: str,
            system: str,
            messages: list[Message],
            temperature: float | None = None,
        ) -> Completion:
            with self.lock:
                if self.budget <= 0:
                    raise QuotaExhausted(f"{model}: daily quota exhausted")
                self.budget -= 1
            return Completion(text=CORRECT)

    class HealthyKey:
        def generate(
            self,
            model: str,
            system: str,
            messages: list[Message],
            temperature: float | None = None,
        ) -> Completion:
            return Completion(text=CORRECT)

    dying = DyingKey(budget=3)
    pool = PooledClient([dying, HealthyKey()])

    run_dir: Path = run_experiment(
        make_config(tmp_path),
        pool,
        conditions=list(PAIRED),
        tasks=MANY,
        workers=4,
    )

    for condition in PAIRED:
        ids = [
            json.loads(line)["task_id"]
            for line in (run_dir / f"{condition.value}.jsonl").read_text().splitlines()
        ]
        assert sorted(ids) == sorted(task.task_id for task in MANY)

    usage = {entry["key"]: entry for entry in pool.usage()}
    assert "gen" in usage["key1"]["exhausted"]  # the dead key was retired
    assert usage["key2"]["calls"] > 0  # and the survivor took over


def test_pending_work_counts_only_what_a_resume_still_owes(tmp_path: Path) -> None:
    """Regression: the counter read `tasks x conditions` and ended at 172/200."""
    from arc_experiment.experiment import pending_work

    config = make_config(tmp_path)
    run_dir: Path = config.results_dir / "runs" / "resume"
    run_dir.mkdir(parents=True)

    assert pending_work(run_dir, TASKS, PAIRED) == 4  # 2 tasks x 2 conditions

    run_experiment(
        config, ScriptedClient(default=CORRECT), conditions=[Condition.SAMPLING],
        tasks=TASKS[:1], run_id="resume",
    )
    # One task now owes only the critic condition; the other still owes both.
    assert pending_work(run_dir, TASKS, PAIRED) == 3
