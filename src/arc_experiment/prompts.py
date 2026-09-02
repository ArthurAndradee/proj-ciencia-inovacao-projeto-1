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

Your only job: compare the rule AND the code stated by the generator against the
ground truth, and report where either contradicts it. The code is what will
actually run, so check whether it truly implements the stated rule, not just
whether the rule sounds right on its own.

Hard constraints, checked automatically:
* NEVER write grids, grid rows, cell values, coordinates lists or colour maps.
* NEVER write code, pseudo-code, or step-by-step instructions to fix the rule.
* NEVER describe the target output. Describe only what the stated rule and code get wrong.
* Refer to examples by index ("training example 2", "the test input").

Answer in exactly these three sections, in prose, at most 150 words in total:

## CONTRADICTIONS
Concrete points where the stated rule, or what the code actually does, is
incompatible with the ground truth.

## COUNTEREXAMPLE
The single example that most clearly falsifies the rule or the code, and which
claim it falsifies, in words only.

## SCOPE
Whether the rule/code is too specific (fits some examples only) or too general
(would also produce outputs that the ground truth excludes).
"""

CRITIC_NO_ORACLE_SYSTEM = """You are a consistency reviewer in a program synthesis experiment.

You do NOT see the task's ground truth and do NOT know whether the candidate is
actually correct. You see only the training pairs, the stated rule, the code,
and how the code performed on the training pairs. You are not a solver. You
never propose a rule, a strategy, an algorithm or code.

Your only job: check whether the code actually implements the stated rule, and
whether the rule itself is consistent with the training pairs you can see.

Hard constraints, checked automatically:
* NEVER write grids, grid rows, cell values, coordinates lists or colour maps.
* NEVER write code, pseudo-code, or step-by-step instructions to fix the rule.
* Refer to examples by index ("training example 2").

Answer in exactly these three sections, in prose, at most 150 words in total:

## CODE/RULE MISMATCH
Concrete points where the code does not actually do what the stated rule claims.

## TRAINING COUNTEREXAMPLE
The single training example that most clearly contradicts the stated rule, or
that the execution report shows the code getting wrong, and which claim it
falsifies. If none, say so.

## SCOPE
Whether the rule is too specific or too general relative to the training pairs
alone (you cannot judge this against the test input, which you cannot see).
"""

CRITIC_CEGIS_SYSTEM = """You are a validation oracle in a program synthesis experiment.

You can see the task's ground truth, including the target output for the test
input, which the other agent CANNOT see. You are not a solver. You never propose
a rule, a strategy, an algorithm or code.

Your only job: find ONE counterexample where the rule or the code contradicts
the ground truth, and classify the kind of correction it needs. No prose beyond
that: this is a structured signal, not an explanation.

Hard constraints, checked automatically:
* NEVER write grids, grid rows, cell values, coordinates lists or colour maps.
* NEVER write code, pseudo-code, or step-by-step instructions to fix the rule.
* NEVER describe the target output.
* Refer to examples by index ("training example 2", "the test input").

Answer in exactly these two sections. Nothing else.

## COUNTEREXAMPLE
Which single example (a training index, or "the test input") falsifies the
rule or the code. One sentence, no more.

## CORRECTION CLASS
Exactly one label from: MISSING_CASE | WRONG_TRANSFORM | WRONG_GEOMETRY | WRONG_COLOR_MAP | WRONG_SCOPE | OTHER
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


def _candidate_block(rule: str, code: str) -> str:
    return (
        f"RULE STATED BY THE GENERATOR:\n{rule}\n\n"
        f"CODE STATED BY THE GENERATOR:\n```python\n{code}\n```"
    )


def critic_request(task: Task, rule: str, code: str, result: RunResult) -> str:
    """Critic input: full ground truth (test output included), the stated rule and code."""
    return (
        f"Task {task.task_id}.\n\n"
        f"GROUND TRUTH — TRAINING:\n{render_pairs(task.train, 'TRAINING EXAMPLE')}\n\n"
        f"GROUND TRUTH — TEST:\nTEST INPUT:\n{grids.render(task.test_pair.input)}\n"
        f"TEST OUTPUT (never disclose):\n{grids.render(task.test_pair.output)}\n\n"
        f"{_candidate_block(rule, code)}\n\n"
        f"EXECUTION OF ITS PROGRAM ON THE TRAINING PAIRS:\n"
        f"{execution_report(result)}\n\n"
        "Report the contradictions between the stated rule/code and the ground truth."
    )


def critic_request_no_oracle(task: Task, rule: str, code: str, result: RunResult) -> str:
    """Critic input with NO test ground truth: training pairs, the stated rule and code only."""
    return (
        f"Task {task.task_id}.\n\n"
        f"TRAINING PAIRS:\n{render_pairs(task.train, 'TRAINING EXAMPLE')}\n\n"
        f"{_candidate_block(rule, code)}\n\n"
        f"EXECUTION OF ITS PROGRAM ON THE TRAINING PAIRS:\n"
        f"{execution_report(result)}\n\n"
        "Check whether the code implements the stated rule, and whether the rule "
        "is consistent with the training pairs above."
    )


def critic_request_cegis(task: Task, rule: str, code: str, result: RunResult) -> str:
    """Critic input for the CEGIS-style critic: same ground truth as `critic_request`."""
    return (
        f"Task {task.task_id}.\n\n"
        f"GROUND TRUTH — TRAINING:\n{render_pairs(task.train, 'TRAINING EXAMPLE')}\n\n"
        f"GROUND TRUTH — TEST:\nTEST INPUT:\n{grids.render(task.test_pair.input)}\n"
        f"TEST OUTPUT (never disclose):\n{grids.render(task.test_pair.output)}\n\n"
        f"{_candidate_block(rule, code)}\n\n"
        f"EXECUTION OF ITS PROGRAM ON THE TRAINING PAIRS:\n"
        f"{execution_report(result)}\n\n"
        "Return one counterexample and one correction class, in the required format."
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
