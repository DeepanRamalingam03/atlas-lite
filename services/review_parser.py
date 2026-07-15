from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ReviewDecision:
    approved: bool
    decision: str
    reason: str
    fix_instruction: str


class ReviewParser:
    """Parses structured manager review responses."""

    def parse(self, review: str) -> ReviewDecision:
        cleaned_review = review.strip()

        if not cleaned_review:
            raise ValueError("Manager review cannot be empty.")

        decision = self._extract_section(
            text=cleaned_review,
            marker="DECISION:",
            next_markers=("REASON:", "FIX_INSTRUCTION:"),
        ).upper()

        reason = self._extract_section(
            text=cleaned_review,
            marker="REASON:",
            next_markers=("FIX_INSTRUCTION:",),
        )

        fix_instruction = self._extract_section(
            text=cleaned_review,
            marker="FIX_INSTRUCTION:",
            next_markers=(),
        )

        if decision not in {"APPROVED", "REJECTED"}:
            raise ValueError(
                "Manager review decision must be APPROVED or REJECTED."
            )

        approved = decision == "APPROVED"

        if approved:
            fix_instruction = "NONE"
        elif not fix_instruction or fix_instruction.upper() == "NONE":
            fix_instruction = (
                "Correct every issue described in the manager review."
            )

        return ReviewDecision(
            approved=approved,
            decision=decision,
            reason=reason,
            fix_instruction=fix_instruction,
        )

    @staticmethod
    def _extract_section(
        text: str,
        marker: str,
        next_markers: tuple[str, ...],
    ) -> str:
        upper_text = text.upper()
        marker_index = upper_text.find(marker)

        if marker_index == -1:
            raise ValueError(
                f"Manager review is missing required section: {marker}"
            )

        content_start = marker_index + len(marker)
        content_end = len(text)

        for next_marker in next_markers:
            next_index = upper_text.find(next_marker, content_start)

            if next_index != -1:
                content_end = min(content_end, next_index)

        return text[content_start:content_end].strip()
