from __future__ import annotations


class PromptBuilder:
    """Builds clean initial and retry prompts for the coding worker."""

    def build_initial_prompt(
        self,
        goal: str,
        manager_instruction: str,
    ) -> str:
        cleaned_goal = goal.strip()
        cleaned_instruction = manager_instruction.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        if not cleaned_instruction:
            raise ValueError("Manager instruction cannot be empty.")

        return (
            "HIGH-LEVEL GOAL\n"
            "===============\n"
            f"{cleaned_goal}\n\n"
            "MANAGER INSTRUCTION\n"
            "===================\n"
            f"{cleaned_instruction}\n\n"
            "Return valid JSON only with complete file contents."
        )

    def build_retry_prompt(
        self,
        goal: str,
        manager_instruction: str,
        manager_review: str,
        test_output: str,
    ) -> str:
        cleaned_goal = goal.strip()
        cleaned_instruction = manager_instruction.strip()
        cleaned_review = manager_review.strip()
        cleaned_test_output = test_output.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        if not cleaned_instruction:
            raise ValueError("Manager instruction cannot be empty.")

        if not cleaned_review:
            cleaned_review = "No manager review was returned."

        if not cleaned_test_output:
            cleaned_test_output = "No test diagnostics were produced."

        return (
            "HIGH-LEVEL GOAL\n"
            "===============\n"
            f"{cleaned_goal}\n\n"
            "ORIGINAL MANAGER INSTRUCTION\n"
            "============================\n"
            f"{cleaned_instruction}\n\n"
            "MANAGER REVIEW\n"
            "==============\n"
            f"{cleaned_review}\n\n"
            "TEST DIAGNOSTICS\n"
            "================\n"
            f"{cleaned_test_output}\n\n"
            "Correct every identified issue.\n"
            "Return valid JSON only.\n"
            "Return every created or modified file with complete content."
        )
