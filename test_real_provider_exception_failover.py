from __future__ import annotations

import unittest

from workers.base_worker import BaseWorker
from workers.fallback_worker import (
    FallbackWorker,
)


class StructuredServerError(
    RuntimeError
):
    def __init__(self) -> None:
        super().__init__(
            {
                "error": {
                    "code": 504,
                    "status": (
                        "DEADLINE_EXCEEDED"
                    ),
                }
            }
        )

        self.code = 504
        self.status = (
            "DEADLINE_EXCEEDED"
        )


class FailingProvider(
    BaseWorker
):
    def execute(
        self,
        instruction: str,
    ) -> str:
        raise StructuredServerError()


class WorkingProvider(
    BaseWorker
):
    def __init__(self) -> None:
        self.calls = 0

    def execute(
        self,
        instruction: str,
    ) -> str:
        self.calls += 1

        return (
            '{"summary":"OpenAI worker used",'
            '"files":[]}'
        )


class RealProviderExceptionFailoverTest(
    unittest.TestCase
):
    def test_structured_504_reaches_fallback(
        self,
    ) -> None:
        fallback = WorkingProvider()

        worker = FallbackWorker(
            workers=(
                (
                    "gemini",
                    FailingProvider(),
                ),
                (
                    "openai",
                    fallback,
                ),
            )
        )

        result = worker.execute(
            "Implement the task."
        )

        self.assertIn(
            "OpenAI worker used",
            result,
        )

        self.assertEqual(
            fallback.calls,
            1,
        )

        self.assertEqual(
            [
                attempt.provider
                for attempt
                in worker.last_attempts
            ],
            [
                "gemini",
                "openai",
            ],
        )

        self.assertFalse(
            worker.last_attempts[0]
            .successful
        )

        self.assertTrue(
            worker.last_attempts[1]
            .successful
        )


if __name__ == "__main__":
    unittest.main()
