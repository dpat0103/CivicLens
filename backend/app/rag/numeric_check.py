"""
Post-generation numeric verification.

Routing keeps value questions away from the model entirely, but explanatory
answers are written from fact cards full of figures, and a model can still
misquote one. The system prompt asks it not to. This check makes sure it
did not: every number in the generated text must appear in the context the
model was given, or the generated answer is discarded.

Deterministic on purpose. A second model call to judge the first would put
the guarantee back on the kind of component it exists to check.
"""

from __future__ import annotations

import re

# A number with optional currency sign, thousands separators, decimals and
# percent sign: 7, 2023, 2,410, $1,250.50, 10.9%, 0.12.
_NUMBER = re.compile(r"\$?\d[\d,]*(?:\.\d+)?%?")


def extract_numbers(text: str) -> set[float]:
    """Every number in `text`, normalized so formatting does not matter.

    "$2,410", "2,410" and "2410" are the same figure, as are "10.9%" and
    "10.9". Signs are dropped because prose says "down 4.1%" where a table
    says -4.1, and the magnitude is what has to be grounded.
    """
    found: set[float] = set()
    for match in _NUMBER.finditer(text):
        digits = match.group().rstrip(",").replace("$", "").replace("%", "").replace(",", "")
        try:
            found.add(round(float(digits), 6))
        except ValueError:
            continue
    return found


def ungrounded_numbers(generated: str, context: str) -> list[float]:
    """Numbers in `generated` that do not appear anywhere in `context`."""
    return sorted(extract_numbers(generated) - extract_numbers(context))
