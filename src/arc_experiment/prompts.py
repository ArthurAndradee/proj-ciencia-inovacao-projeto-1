"""Prompt construction for both roles.

Scope isolation is the core of the experiment and lives here:

* the generator never sees the test output, in either condition;
* the critic sees the test output but is forbidden from proposing code or
  restating any grid (enforced downstream by `guards.sanitize`).
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


def generator_revision(feedback: str, result: RunResult) -> str:
    """Intervention follow-up: execution outcome plus the critic's sanitized feedback."""
    return (
        f"{execution_report(result)}\n\n"
        "An independent validator, which can see the ground truth you cannot, "
        "reviewed the rule you stated and reported:\n\n"
        f"{feedback}\n\n"
        "The validator gives no solutions and may be partially wrong. Use it to "
        "find the flaw in your own reasoning, restate the rule and rewrite the "
        f"program. Answer again with both sections ({RULE_HEADER} and {CODE_HEADER})."
    )
