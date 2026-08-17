"""Leak guard applied to the critic's feedback.

The critic is the only agent that sees the test-pair ground truth. Its feedback
must describe contradictions in the generator's stated rule, never the target
state itself. This module redacts anything that would smuggle the answer through:
grid-shaped digit rows and code blocks.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

REDACTION = "[REDACTED: leaked grid or code]"

# A line made only of three or more integers: a serialized grid row or a
# coordinate/colour list. Multi-digit values are covered too, so the guard does
# not depend on ARC's 0-9 alphabet.
_GRID_ROW = re.compile(r"^[^\n\w]*(?:\d+[ ,\t]+){2,}\d+[^\n\w]*$", re.MULTILINE)
# Fenced code blocks of any language.
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
# Python statements the critic has no business emitting.
_CODE_LINE = re.compile(r"^\s*(?:def |import |from \w+ import |return |for |while ).*$", re.MULTILINE)


@dataclass(frozen=True)
class Sanitized:
    text: str
    violations: list[str]

    @property
    def leaked(self) -> bool:
        return bool(self.violations)


def sanitize(text: str) -> Sanitized:
    """Redact grid rows and code from critic feedback, reporting what was hit."""
    violations: list[str] = []
    cleaned: str = text

    for label, pattern in (
        ("code_fence", _CODE_FENCE),
        ("grid_row", _GRID_ROW),
        ("code_line", _CODE_LINE),
    ):
        cleaned, hits = pattern.subn(REDACTION, cleaned)
        violations.extend([label] * hits)

    return Sanitized(text=cleaned, violations=violations)
