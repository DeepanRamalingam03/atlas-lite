from __future__ import annotations

import unittest

from workers.base_worker import BaseWorker
from workers.fallback_worker import (
    FallbackWorker,
    WorkerProviderError,
)


class FakeWorker(BaseWorker):
    def __init__(
        self,
        *,
        response: str = "",
        error: Exception | None = None,
    ) -> None:
        self.response = response
        self.error = error
        self.calls: list[str] = []

    def execute(
        self,
        instruction: str,
    ) -> str:
        self.calls.append(instruction)

        if self.error is not None:
            raise self.error

        return self.response


class FallbackWorkerTest(
    unittest.TestCase
):
    def test_primary_success_does_not_call_fallback(
        self,
    ) -> None:
        primary = FakeWorker(
            response='{"summary":"ok","files":[]}'
        )

        fallback = FakeWorker(
            response="unused"
        )

        worker = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        )

        result = worker.execute(
            "Build feature."
        )

        self.assertIn(
            '"summary":"ok"',
            result,
        )

        self.assertEqual(
            len(primary.calls),
            1,
        )

        self.assertEqual(
            fallback.calls,
            [],
        )

        self.assertEqual(
            worker.last_attempts[0].provider,
            "gemini",
        )

        self.assertTrue(
            worker.last_attempts[0].successful
        )

    def test_504_uses_openai_fallback(
        self,
    ) -> None:
        primary = FakeWorker(
            error=RuntimeError(
                "504 DEADLINE_EXCEEDED"
            )
        )

        fallback = FakeWorker(
            response=(
                '{"summary":"fallback",'
                '"files":[]}'
            )
        )

        worker = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        )

        result = worker.execute(
            "Build feature."
        )

        self.assertIn(
            "fallback",
            result,
        )

        self.assertEqual(
            len(primary.calls),
            1,
        )

        self.assertEqual(
            len(fallback.calls),
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

    def test_503_uses_fallback(
        self,
    ) -> None:
        primary = FakeWorker(
            error=RuntimeError(
                "503 UNAVAILABLE: high demand"
            )
        )

        fallback = FakeWorker(
            response="valid response"
        )

        result = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        ).execute(
            "Build feature."
        )

        self.assertEqual(
            result,
            "valid response",
        )

    def test_timeout_uses_fallback(
        self,
    ) -> None:
        primary = FakeWorker(
            error=TimeoutError(
                "request timed out"
            )
        )

        fallback = FakeWorker(
            response="fallback response"
        )

        result = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        ).execute(
            "Build feature."
        )

        self.assertEqual(
            result,
            "fallback response",
        )

    def test_non_transient_error_does_not_fallback(
        self,
    ) -> None:
        primary = FakeWorker(
            error=ValueError(
                "Invalid worker instruction"
            )
        )

        fallback = FakeWorker(
            response="must not run"
        )

        worker = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        )

        with self.assertRaises(
            ValueError
        ):
            worker.execute(
                "Build feature."
            )

        self.assertEqual(
            fallback.calls,
            [],
        )

    def test_all_provider_failures_are_reported(
        self,
    ) -> None:
        primary = FakeWorker(
            error=RuntimeError(
                "503 UNAVAILABLE"
            )
        )

        fallback = FakeWorker(
            error=TimeoutError(
                "OpenAI timeout"
            )
        )

        worker = FallbackWorker(
            workers=(
                ("gemini", primary),
                ("openai", fallback),
            )
        )

        with self.assertRaises(
            WorkerProviderError
        ) as captured:
            worker.execute(
                "Build feature."
            )

        error = str(
            captured.exception
        )

        self.assertIn(
            "gemini",
            error,
        )

        self.assertIn(
            "openai",
            error,
        )

        self.assertEqual(
            len(
                captured.exception.attempts
            ),
            2,
        )

    def test_empty_instruction_is_rejected(
        self,
    ) -> None:
        worker = FallbackWorker(
            workers=(
                (
                    "gemini",
                    FakeWorker(
                        response="unused"
                    ),
                ),
            )
        )

        with self.assertRaises(
            ValueError
        ):
            worker.execute("   ")

    def test_duplicate_provider_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            FallbackWorker(
                workers=(
                    (
                        "gemini",
                        FakeWorker(
                            response="one"
                        ),
                    ),
                    (
                        "gemini",
                        FakeWorker(
                            response="two"
                        ),
                    ),
                )
            )


if __name__ == "__main__":
    unittest.main()
