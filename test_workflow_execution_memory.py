from __future__ import annotations

import unittest

from services.execution_memory.workflow_memory import (
    WorkflowExecutionMemory,
)


class WorkflowExecutionMemoryTest(
    unittest.TestCase
):
    def test_empty_memory_has_empty_context(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        context = memory.build_context()

        self.assertEqual(
            context.attempt_count,
            0,
        )

        self.assertEqual(
            context.repeated_failure_count,
            0,
        )

        self.assertEqual(
            context.rendered_context,
            "",
        )

    def test_record_and_render_attempt(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        attempt = memory.record(
            iteration=1,
            summary="Added utility.",
            changed_paths=[
                "services/utility.py",
                "test_utility.py",
            ],
            test_success=False,
            review_approved=False,
            review_reason=(
                "Validation failed."
            ),
            fix_instruction=(
                "Correct the return type."
            ),
        )

        context = memory.build_context()

        self.assertEqual(
            attempt.iteration,
            1,
        )

        self.assertEqual(
            context.attempt_count,
            1,
        )

        self.assertIn(
            "WORKFLOW EXECUTION MEMORY",
            context.rendered_context,
        )

        self.assertIn(
            "services/utility.py",
            context.rendered_context,
        )

        self.assertIn(
            "Correct the return type.",
            context.rendered_context,
        )

    def test_duplicate_iteration_is_rejected(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        memory.record(
            iteration=1,
            summary="First.",
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason="Rejected.",
            fix_instruction="Fix.",
        )

        with self.assertRaisesRegex(
            ValueError,
            "already exists",
        ):
            memory.record(
                iteration=1,
                summary="Duplicate.",
                changed_paths=[],
                test_success=False,
                review_approved=False,
                review_reason="Rejected.",
                fix_instruction="Fix.",
            )

    def test_repeated_failure_is_detected(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        for iteration in (
            1,
            2,
        ):
            memory.record(
                iteration=iteration,
                summary="Same attempt.",
                changed_paths=[
                    "module.py"
                ],
                test_success=False,
                review_approved=False,
                review_reason=(
                    "Tests failed."
                ),
                fix_instruction=(
                    "Correct implementation."
                ),
            )

        context = memory.build_context()

        self.assertEqual(
            context.repeated_failure_count,
            2,
        )

        self.assertIn(
            "REPEATED FAILURE WARNING",
            context.rendered_context,
        )

        self.assertIn(
            "materially different correction",
            context.rendered_context,
        )

    def test_different_failures_are_not_combined(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        memory.record(
            iteration=1,
            summary="Attempt one.",
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason="Syntax failed.",
            fix_instruction="Fix syntax.",
        )

        memory.record(
            iteration=2,
            summary="Attempt two.",
            changed_paths=[],
            test_success=True,
            review_approved=False,
            review_reason=(
                "Architecture rejected."
            ),
            fix_instruction=(
                "Use existing service."
            ),
        )

        context = memory.build_context()

        self.assertEqual(
            context.repeated_failure_count,
            1,
        )

        self.assertNotIn(
            "REPEATED FAILURE WARNING",
            context.rendered_context,
        )

    def test_successful_attempt_is_recorded(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        memory.record(
            iteration=1,
            summary="Completed feature.",
            changed_paths=[
                "feature.py"
            ],
            test_success=True,
            review_approved=True,
            review_reason="Approved.",
            fix_instruction="NONE",
        )

        context = memory.build_context()

        self.assertIn(
            "Tests passed: True",
            context.rendered_context,
        )

        self.assertIn(
            "Manager approved: True",
            context.rendered_context,
        )

        self.assertEqual(
            context.repeated_failure_count,
            0,
        )

    def test_attempt_limit_keeps_newest_records(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory(
            max_attempts=2
        )

        for iteration in (
            1,
            2,
            3,
        ):
            memory.record(
                iteration=iteration,
                summary=(
                    f"Attempt {iteration}."
                ),
                changed_paths=[],
                test_success=False,
                review_approved=False,
                review_reason=(
                    f"Failure {iteration}."
                ),
                fix_instruction=(
                    f"Fix {iteration}."
                ),
            )

        attempts = memory.list_attempts()

        self.assertEqual(
            [
                item.iteration
                for item in attempts
            ],
            [2, 3],
        )

    def test_paths_are_deduplicated_and_safe(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        attempt = memory.record(
            iteration=1,
            summary="Files.",
            changed_paths=[
                "services/a.py",
                "services/a.py",
                "../secret.env",
                "/etc/passwd",
                r"tests\test_a.py",
            ],
            test_success=False,
            review_approved=False,
            review_reason="Rejected.",
            fix_instruction="Fix.",
        )

        self.assertEqual(
            attempt.changed_paths,
            (
                "services/a.py",
                "tests/test_a.py",
            ),
        )

    def test_path_limit_is_enforced(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory(
            max_paths_per_attempt=2
        )

        attempt = memory.record(
            iteration=1,
            summary="Files.",
            changed_paths=[
                "a.py",
                "b.py",
                "c.py",
            ],
            test_success=False,
            review_approved=False,
            review_reason="Rejected.",
            fix_instruction="Fix.",
        )

        self.assertEqual(
            attempt.changed_paths,
            (
                "a.py",
                "b.py",
            ),
        )

    def test_sensitive_values_are_redacted(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        attempt = memory.record(
            iteration=1,
            summary=(
                "api_key=super-secret-value"
            ),
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason=(
                "Bearer abcdefghijklmnop"
            ),
            fix_instruction=(
                "Use token: secret-token-value"
            ),
        )

        serialized = "\n".join(
            [
                attempt.summary,
                attempt.review_reason,
                attempt.fix_instruction,
            ]
        )

        self.assertNotIn(
            "super-secret-value",
            serialized,
        )

        self.assertNotIn(
            "abcdefghijklmnop",
            serialized,
        )

        self.assertNotIn(
            "secret-token-value",
            serialized,
        )

        self.assertIn(
            "[REDACTED]",
            serialized,
        )

    def test_fields_are_bounded(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory(
            max_field_characters=120
        )

        attempt = memory.record(
            iteration=1,
            summary="x" * 500,
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason="y" * 500,
            fix_instruction="z" * 500,
        )

        self.assertLessEqual(
            len(attempt.summary),
            120,
        )

        self.assertLessEqual(
            len(attempt.review_reason),
            120,
        )

        self.assertLessEqual(
            len(attempt.fix_instruction),
            120,
        )

        self.assertTrue(
            attempt.summary.endswith(
                "[truncated]"
            )
        )

    def test_context_is_bounded(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory(
            max_attempts=6,
            max_field_characters=500,
            max_context_characters=1_200,
        )

        for iteration in range(
            1,
            7,
        ):
            memory.record(
                iteration=iteration,
                summary="summary " * 100,
                changed_paths=[
                    f"file_{iteration}.py"
                ],
                test_success=False,
                review_approved=False,
                review_reason=(
                    "review reason " * 100
                ),
                fix_instruction=(
                    "fix instruction " * 100
                ),
            )

        context = memory.build_context()

        self.assertLessEqual(
            len(context.rendered_context),
            1_200,
        )

        self.assertIn(
            "EXECUTION MEMORY TRUNCATED",
            context.rendered_context,
        )

    def test_clear_removes_all_attempts(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        memory.record(
            iteration=1,
            summary="Attempt.",
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason="Rejected.",
            fix_instruction="Fix.",
        )

        memory.clear()

        self.assertEqual(
            memory.list_attempts(),
            (),
        )

        self.assertEqual(
            memory.build_context()
            .rendered_context,
            "",
        )

    def test_latest_returns_newest_attempt(
        self,
    ) -> None:
        memory = WorkflowExecutionMemory()

        memory.record(
            iteration=1,
            summary="First.",
            changed_paths=[],
            test_success=False,
            review_approved=False,
            review_reason="Rejected.",
            fix_instruction="Fix.",
        )

        memory.record(
            iteration=2,
            summary="Second.",
            changed_paths=[],
            test_success=True,
            review_approved=True,
            review_reason="Approved.",
            fix_instruction="NONE",
        )

        latest = memory.latest()

        self.assertIsNotNone(latest)

        assert latest is not None

        self.assertEqual(
            latest.iteration,
            2,
        )

        self.assertEqual(
            latest.summary,
            "Second.",
        )


if __name__ == "__main__":
    unittest.main()
