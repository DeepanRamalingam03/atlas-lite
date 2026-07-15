from __future__ import annotations

from services.review_parser import ReviewParser


parser = ReviewParser()

approved = parser.parse(
    """
DECISION: APPROVED

REASON:
Implementation is correct.

FIX_INSTRUCTION:
NONE
"""
)

assert approved.approved is True
assert approved.decision == "APPROVED"
assert approved.fix_instruction == "NONE"

rejected = parser.parse(
    """
DECISION: REJECTED

REASON:
Type annotations are missing.

FIX_INSTRUCTION:
Add type annotations.
"""
)

assert rejected.approved is False
assert rejected.decision == "REJECTED"
assert rejected.reason == "Type annotations are missing."
assert rejected.fix_instruction == "Add type annotations."

print("Review parser passed")
