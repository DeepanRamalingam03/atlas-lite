from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from run_continuous_runtime import (
    build_pipeline,
)
from services.execution_memory.workflow_memory import (
    WorkflowExecutionMemory,
)


class FakeClient:
    def generate(
        self,
        prompt: str,
    ) -> str:
        return "unused"


class Phase35RuntimeMemoryTest(
    unittest.TestCase
):
    def test_production_memory_is_enabled(
        self,
    ) -> None:
        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            return_value=FakeClient(),
        ):
            with patch.dict(
                os.environ,
                {
                    "ATLAS_EXECUTION_MEMORY_ENABLED": (
                        "true"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_ATTEMPTS": (
                        "4"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_PATHS": (
                        "20"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_FIELD_CHARACTERS": (
                        "1200"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_CONTEXT_CHARACTERS": (
                        "8000"
                    ),
                },
            ):
                pipeline = build_pipeline()

        self.assertIsNotNone(
            pipeline.execution_memory_factory
        )

        assert (
            pipeline.execution_memory_factory
            is not None
        )

        first = (
            pipeline.execution_memory_factory()
        )

        second = (
            pipeline.execution_memory_factory()
        )

        self.assertIsInstance(
            first,
            WorkflowExecutionMemory,
        )

        self.assertIsNot(
            first,
            second,
        )

        self.assertEqual(
            first.max_attempts,
            4,
        )

        self.assertEqual(
            first.max_paths_per_attempt,
            20,
        )

        self.assertEqual(
            first.max_field_characters,
            1200,
        )

        self.assertEqual(
            first.max_context_characters,
            8000,
        )

    def test_production_memory_can_be_disabled(
        self,
    ) -> None:
        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            return_value=FakeClient(),
        ):
            with patch.dict(
                os.environ,
                {
                    "ATLAS_EXECUTION_MEMORY_ENABLED": (
                        "false"
                    ),
                },
            ):
                pipeline = build_pipeline()

        self.assertIsNone(
            pipeline.execution_memory_factory
        )

    def test_invalid_attempt_limit_fails_safely(
        self,
    ) -> None:
        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            return_value=FakeClient(),
        ):
            with patch.dict(
                os.environ,
                {
                    "ATLAS_EXECUTION_MEMORY_ENABLED": (
                        "true"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_ATTEMPTS": (
                        "0"
                    ),
                },
            ):
                with self.assertRaises(
                    RuntimeError
                ):
                    build_pipeline()

    def test_invalid_context_limit_fails_safely(
        self,
    ) -> None:
        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            return_value=FakeClient(),
        ):
            with patch.dict(
                os.environ,
                {
                    "ATLAS_EXECUTION_MEMORY_ENABLED": (
                        "true"
                    ),
                    "ATLAS_EXECUTION_MEMORY_MAX_CONTEXT_CHARACTERS": (
                        "500"
                    ),
                },
            ):
                with self.assertRaises(
                    RuntimeError
                ):
                    build_pipeline()

    def test_default_memory_limits_are_bounded(
        self,
    ) -> None:
        environment = {
            key: value
            for key, value
            in os.environ.items()
            if not key.startswith(
                "ATLAS_EXECUTION_MEMORY_"
            )
        }

        with patch(
            "run_continuous_runtime."
            "ClientFactory.create",
            return_value=FakeClient(),
        ):
            with patch.dict(
                os.environ,
                environment,
                clear=True,
            ):
                pipeline = build_pipeline()

        assert (
            pipeline.execution_memory_factory
            is not None
        )

        memory = (
            pipeline.execution_memory_factory()
        )

        self.assertEqual(
            memory.max_attempts,
            6,
        )

        self.assertEqual(
            memory.max_paths_per_attempt,
            30,
        )

        self.assertEqual(
            memory.max_field_characters,
            1500,
        )

        self.assertEqual(
            memory.max_context_characters,
            10000,
        )


if __name__ == "__main__":
    unittest.main()
