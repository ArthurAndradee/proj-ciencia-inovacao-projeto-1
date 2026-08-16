import argparse
import json
from pathlib import Path

import pytest

from arc_experiment import cli
from arc_experiment.config import REPO_ROOT, Config
from arc_experiment.runner import Condition

# The conditions a default `run` pairs.
PAIRED: tuple[Condition, ...] = (Condition.SAMPLING, Condition.CRITIC)


@pytest.fixture(autouse=True)
def isolated_results(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep runs out of the repository and away from the developer's .env."""
    monkeypatch.setenv("RESULTS_DIR", str(tmp_path / "results"))
    monkeypatch.setenv("DATA_DIR", str(REPO_ROOT / "data"))
    monkeypatch.setenv("GOOGLE_API_KEY", "")


def parse(argv: list[str]) -> argparse.Namespace:
    return cli.build_parser().parse_args(argv)


def test_modes_map_to_conditions() -> None:
    assert cli.MODES["sampling"] == (Condition.SAMPLING,)
    assert cli.MODES["critic"] == (Condition.CRITIC,)
    assert cli.MODES["both"] == (Condition.SAMPLING, Condition.CRITIC)


def test_pacing_note_reports_the_throttled_wall_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RPM", "10")
    monkeypatch.setenv("BUDGET_CALLS", "7")
    note: str = cli.pacing_note(10, Config.from_env())
    # A floor, explicitly: model latency is not in it and can dominate.
    assert "6s between calls" in note and "at least ~7 min" in note
    assert "latency adds on top" in note


def test_task_and_sample_are_mutually_exclusive() -> None:
    with pytest.raises(SystemExit):
        parse(["run", "--task", "007bbfb7", "--sample", "5"])


def test_cli_overrides_beat_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "1")
    monkeypatch.setenv("BUDGET_CALLS", "12")
    config: Config = cli.config_from_args(
        parse(["run", "--sample", "3", "--seed", "99", "--budget", "5", "--split", "training"])
    )
    assert (config.seed, config.budget_calls, config.sample_size) == (99, 5, 3)
    assert config.split == "training"


def test_environment_is_kept_when_no_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SEED", "1234")
    assert cli.config_from_args(parse(["run", "--sample", "2"])).seed == 1234


def test_resolve_tasks_by_id() -> None:
    config: Config = cli.config_from_args(parse(["run", "--task", "007bbfb7"]))
    tasks = cli.resolve_tasks(parse(["run", "--task", "007bbfb7"]), config)
    assert [task.task_id for task in tasks] == ["007bbfb7"]


def test_tasks_file_selects_the_listed_ids(tmp_path: Path) -> None:
    listing: Path = tmp_path / "ids.txt"
    listing.write_text("# a fixed subset\n007bbfb7\n\n00d62c1b  # trailing comment\n")
    args = parse(["run", "--tasks-file", str(listing)])
    tasks = cli.resolve_tasks(args, cli.config_from_args(args))
    assert [task.task_id for task in tasks] == ["007bbfb7", "00d62c1b"]


def test_an_empty_tasks_file_is_rejected(tmp_path: Path) -> None:
    listing: Path = tmp_path / "empty.txt"
    listing.write_text("# nothing but comments\n\n")
    with pytest.raises(ValueError, match="no task ids"):
        cli.read_task_ids(listing)


def test_unknown_task_id_is_reported() -> None:
    config: Config = Config.from_env()
    with pytest.raises(FileNotFoundError):
        cli.resolve_tasks(parse(["run", "--task", "nope"]), config)


def test_run_id_for_explicit_tasks_names_the_tasks() -> None:
    args = parse(["run", "--task", "007bbfb7", "--task", "00d62c1b", "--budget", "8"])
    config: Config = cli.config_from_args(args)
    tasks = cli.resolve_tasks(args, config)
    assert cli.default_run_id(args, config, tasks) == "task-007bbfb7+1-b8"


def test_dry_run_writes_results_without_an_api_key(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code: int = cli.main(
        ["run", "--task", "007bbfb7", "--mode", "both", "--budget", "2", "--dry-run"]
    )
    assert exit_code == 0
    output: str = capsys.readouterr().out
    assert "007bbfb7" in output and "Paired comparison" in output

    run_dir: Path = Config.from_env().results_dir / "runs" / "task-007bbfb7-b2"
    for condition in PAIRED:
        records = [
            json.loads(line)
            for line in (run_dir / f"{condition.value}.jsonl").read_text().splitlines()
        ]
        assert [record["task_id"] for record in records] == ["007bbfb7"]
    assert (run_dir / "manifest.json").is_file()


def test_report_rerenders_a_finished_run(capsys: pytest.CaptureFixture[str]) -> None:
    cli.main(["run", "--task", "007bbfb7", "--mode", "sampling", "--budget", "1", "--dry-run"])
    capsys.readouterr()

    assert cli.main(["report", "--run-id", "task-007bbfb7-b1"]) == 0
    output: str = capsys.readouterr().out
    assert "007bbfb7" in output and "sampling" in output


def test_report_on_a_missing_run_fails_cleanly(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["report", "--run-id", "does-not-exist"]) == 1
    assert "not found" in capsys.readouterr().err


def test_fresh_discards_previous_results() -> None:
    argv = ["run", "--task", "007bbfb7", "--mode", "sampling", "--budget", "1", "--dry-run"]
    cli.main(argv)
    path: Path = (
        Config.from_env().results_dir / "runs" / "task-007bbfb7-b1" / "sampling.jsonl"
    )
    cli.main(argv)  # resumed: the task is skipped, the file keeps one line
    assert len(path.read_text().splitlines()) == 1

    cli.main([*argv, "--fresh"])
    assert len(path.read_text().splitlines()) == 1


def test_tasks_lists_the_sampled_ids(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["tasks", "--sample", "3", "--split", "evaluation", "--seed", "1"]) == 0
    output: str = capsys.readouterr().out
    assert "3 task(s)" in output
    assert len([line for line in output.splitlines() if line.startswith("  ")]) == 3
