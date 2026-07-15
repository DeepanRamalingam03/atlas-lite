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
            "Return valid JSON only.\n"
            "Return every created or modified file with complete content."
        )

    def build_retry_prompt(
        self,
        goal: str,
        manager_instruction: str,
        rejection_reason: str,
        fix_instruction: str,
        test_output: str,
        iteration: int,
    ) -> str:
        cleaned_goal = goal.strip()
        cleaned_instruction = manager_instruction.strip()
        cleaned_reason = rejection_reason.strip()
        cleaned_fix = fix_instruction.strip()
        cleaned_test_output = test_output.strip()

        if not cleaned_goal:
            raise ValueError("Goal cannot be empty.")

        if not cleaned_instruction:
            raise ValueError("Manager instruction cannot be empty.")

        if iteration < 1:
            raise ValueError("Iteration must be at least 1.")

        if not cleaned_reason:
            cleaned_reason = "The previous implementation was rejected."

        if not cleaned_fix:
            cleaned_fix = "Correct every identified issue."

        if not cleaned_test_output:
            cleaned_test_output = "No test diagnostics were produced."

        return (
            f"RETRY ITERATION {iteration}\n"
            "=================\n\n"
            "HIGH-LEVEL GOAL\n"
            "===============\n"
            f"{cleaned_goal}\n\n"
            "ORIGINAL MANAGER INSTRUCTION\n"
            "============================\n"
            f"{cleaned_instruction}\n\n"
            "REJECTION REASON\n"
            "================\n"
            f"{cleaned_reason}\n\n"
            "REQUIRED FIX\n"
            "============\n"
            f"{cleaned_fix}\n\n"
            "TEST DIAGNOSTICS\n"
            "================\n"
            f"{cleaned_test_output}\n\n"
            "Return a corrected implementation.\n"
            "Return valid JSON only.\n"
            "Return complete contents for every created or modified file."
        )
