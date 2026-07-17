from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from services.planning.execution_plan_context import (
    ExecutionPlanContextService,
)
from run_continuous_runtime import (
    build_pipeline,
)


class FakeClient:
    def generate(
        self,
        prompt: str,
    ) -> str:
        return "unused"


class Phase34RuntimePlanningTest(
    unittest.TestCase
):
    def test_production_pipeline_enables_planning(
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
                    "ATLAS_PLANNING_ENABLED": "true",
                    "ATLAS_PLANNING_MAX_TASKS": "10",
                    "ATLAS_PLANNING_MAX_CHARACTERS": (
                        "9000"
                    ),
                },
            ):
                pipeline = build_pipeline()

        self.assertIsInstance(
            pipeline.planning_service,
            ExecutionPlanContextService,
        )

        self.assertEqual(
            pipeline.planning_service.max_tasks,
            10,
        )

        self.assertEqual(
            pipeline.planning_service.max_characters,
            9000,
        )

    def test_production_planning_can_be_disabled(
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
                    "ATLAS_PLANNING_ENABLED": "false",
                },
            ):
                pipeline = build_pipeline()

        self.assertIsNone(
            pipeline.planning_service
        )

    def test_invalid_task_limit_fails_safely(
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
                    "ATLAS_PLANNING_ENABLED": "true",
                    "ATLAS_PLANNING_MAX_TASKS": "0",
                },
            ):
                with self.assertRaises(
                    RuntimeError
                ):
                    build_pipeline()


if __name__ == "__main__":
    unittest.main()
