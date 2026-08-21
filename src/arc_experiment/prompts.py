"""Prompt construction for both roles.

Scope isolation is the core of the experiment and lives here:

* the generator never sees the test output, except under the ORACLE arm, where
  `counterexample_block` hands it over deliberately;
* the critic sees the test output but is forbidden from proposing code or
  restating any grid (enforced downstream by `guards.sanitize`).

The injection arms bypass the critic entirely: the grids they disclose are
rendered here, from the ground truth, never asked of the model. What leaks is
therefore exactly what was chosen, identical on every call, and `guards.sanitize`
keeps meaning what it meant — prose the critic should not have written.
"""

from __future__ import annotations

from collections.abc import Sequence

from . import grids
from .dataset import Pair, Task
from .executor import RunResult

RULE_HEADER = "## RULE"
CODE_HEADER = "## CODE"

GENERATOR_SYSTEM = f"""You are a program synthesis agent solving ARC-AGI tasks.

Each task shows input/output grid pairs that share one transformation rule.
Grids are rectangles of integers 0-9, where 0 is the background.

Always answer in exactly two sections:

{RULE_HEADER}
A precise natural-language statement of the transformation rule: what is
detected in the input, and how the output is built from it. State it as a
general rule, not as a description of one example.

{CODE_HEADER}
A single fenced Python block defining `transform(grid: list[list[int]]) -> list[list[int]]`.
The code must use only the Python standard library, must not read files or the
network, must be deterministic, and must return a new grid.
"""

CRITIC_SYSTEM = """You are a validation oracle in a program synthesis experiment.

You can see the task's ground truth, including the target output for the test
input, which the other agent CANNOT see. You are not a solver. You never propose
a rule, a strategy, an algorithm or code.

Your only job: compare the rule stated by the generator against the ground truth
and report where the stated rule contradicts it.

Hard constraints, checked automatically:
* NEVER write grids, grid rows, cell values, coordinates lists or colour maps.
* NEVER write code, pseudo-code, or step-by-step instructions to fix the rule.
* NEVER describe the target output. Describe only what the stated rule gets wrong.
* Refer to examples by index ("training example 2", "the test input").

Answer in exactly these three sections, in prose, at most 150 words in total:

## CONTRADICTIONS
Concrete points where the stated rule is incompatible with the ground truth.

## COUNTEREXAMPLE
The single example that most clearly falsifies the rule, and which claim of the
rule it falsifies, in words only.

## SCOPE
Whether the rule is too specific (fits some examples only) or too general
(would also produce outputs that the ground truth excludes).
"""


def render_pairs(pairs: Sequence[Pair], label: str) -> str:
    blocks: list[str] = []
    for index, pair in enumerate(pairs, start=1):
        blocks.append(
            f"{label} {index} INPUT:\n{grids.render(pair.input)}\n"
            f"{label} {index} OUTPUT:\n{grids.render(pair.output)}"
        )
    return "\n\n".join(blocks)


def generator_initial(task: Task) -> str:
    """First message to the generator: training pairs plus the test input only."""
    return (
        f"Task {task.task_id}.\n\n"
        f"{render_pairs(task.train, 'TRAINING EXAMPLE')}\n\n"
        f"TEST INPUT:\n{grids.render(task.test_pair.input)}\n\n"
        "Infer the rule that maps every training input to its output, then write "
        "`transform` so that it reproduces all training outputs and generalises to "
        "the test input."
    )


def execution_report(result: RunResult) -> str:
    """Objective execution outcome over the training pairs."""
    if not result.ok:
        return f"Your program could not be executed: {result.error}"
    lines: list[str] = [
        f"Your program reproduced {result.n_correct}/{len(result.cases)} training outputs."
    ]
    for index, case in enumerate(result.cases, start=1):
        status: str = "OK" if case.correct else case.diff
        lines.append(f"- training example {index}: {status}")
        if not case.correct and case.got is not None:
            lines.append(f"  your output was:\n{grids.render(case.got)}")
    return "\n".join(lines)


def counterexample_block(task: Task, result: RunResult, *, include_test: bool) -> str:
    """Ground-truth grids appended verbatim to the revision message.

    Only the training pairs the program got wrong: the generator already holds
    every pair in its history, so restating the ones it reproduced spends tokens
    to say nothing. What is new here is the confrontation — the expected grid
    next to the produced one — not the data.

    With `include_test`, the target the generator is not supposed to see is
    appended too. That is the ceiling arm, and it is stated in the prompt rather
    than smuggled: an arm whose whole point is disclosure has nothing to hide.
    """
    blocks: list[str] = []
    for index, case in enumerate(result.cases, start=1):
        if case.correct:
            continue
        blocks.append(
            f"TRAINING EXAMPLE {index} — EXPECTED OUTPUT:\n"
            f"{grids.render(task.train[index - 1].output)}"
        )
    if include_test:
        blocks.append(
            f"TEST INPUT:\n{grids.render(task.test_pair.input)}\n"
            f"TEST OUTPUT — the target your program must reproduce:\n"
            f"{grids.render(task.test_pair.output)}"
        )
    if not blocks:
        return ""
    return "GROUND TRUTH FOR THE CASES YOU MISSED:\n\n" + "\n\n".join(blocks)


def critic_request(task: Task, rule: str, result: RunResult) -> str:
    """Critic input: full ground truth (test output included) and the stated rule."""
    return (
        f"Task {task.task_id}.\n\n"
        f"GROUND TRUTH — TRAINING:\n{render_pairs(task.train, 'TRAINING EXAMPLE')}\n\n"
        f"GROUND TRUTH — TEST:\nTEST INPUT:\n{grids.render(task.test_pair.input)}\n"
        f"TEST OUTPUT (never disclose):\n{grids.render(task.test_pair.output)}\n\n"
        f"RULE STATED BY THE GENERATOR:\n{rule}\n\n"
        f"EXECUTION OF ITS PROGRAM ON THE TRAINING PAIRS:\n"
        f"{execution_report(result)}\n\n"
        "Report the contradictions between the stated rule and the ground truth."
    )


def generator_revision(feedback: str, result: RunResult, counterexample: str = "") -> str:
    """Intervention follow-up: execution outcome plus the critic's sanitized feedback.

    `counterexample` carries the disclosed ground truth of the injection arms and
    goes last, after the critique: the critic's job is to make the generator
    doubt its own rule, and grids placed first would let it skip straight to
    pattern-matching them.
    """
    disclosure: str = f"\n\n{counterexample}" if counterexample else ""
    return (
        f"{execution_report(result)}\n\n"
        "An independent validator, which can see the ground truth you cannot, "
        "reviewed the rule you stated and reported:\n\n"
        f"{feedback}"
        f"{disclosure}\n\n"
        "The validator gives no solutions and may be partially wrong. Use it to "
        "find the flaw in your own reasoning, restate the rule and rewrite the "
        f"program. Answer again with both sections ({RULE_HEADER} and {CODE_HEADER})."
    )
