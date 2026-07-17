from __future__ import annotations

import json
import shutil
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core.usage.token_ledger import (
    TokenUsageLedger,
    TokenUsageRecord,
)


class TokenUsageLedgerTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_token_usage_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.path = (
            self.root / "usage.json"
        )

        self.ledger = TokenUsageLedger(
            storage_path=self.path,
            max_records=3,
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_append_and_reload(
        self,
    ) -> None:
        record = self._record(
            provider="openai",
            input_tokens=10,
            output_tokens=5,
            total_tokens=15,
        )

        self.ledger.append(record)

        reloaded = TokenUsageLedger(
            storage_path=self.path
        ).list_all()

        self.assertEqual(
            reloaded,
            [record],
        )

    def test_summary_totals(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="openai",
                input_tokens=100,
                output_tokens=20,
                total_tokens=120,
                cached_input_tokens=10,
                reasoning_tokens=3,
                latency_ms=50,
            )
        )

        self.ledger.append(
            self._record(
                provider="gemini",
                input_tokens=200,
                output_tokens=40,
                total_tokens=250,
                reasoning_tokens=5,
                tool_tokens=5,
                latency_ms=70,
            )
        )

        summary = self.ledger.summarize()

        self.assertEqual(
            summary.request_count,
            2,
        )

        self.assertEqual(
            summary.input_tokens,
            300,
        )

        self.assertEqual(
            summary.output_tokens,
            60,
        )

        self.assertEqual(
            summary.total_tokens,
            370,
        )

        self.assertEqual(
            summary.reasoning_tokens,
            8,
        )

        self.assertEqual(
            summary.tool_tokens,
            5,
        )

        self.assertEqual(
            summary.average_latency_ms,
            60.0,
        )

    def test_provider_filter(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="openai",
                total_tokens=10,
            )
        )

        self.ledger.append(
            self._record(
                provider="gemini",
                total_tokens=20,
            )
        )

        summary = self.ledger.summarize(
            provider="openai"
        )

        self.assertEqual(
            summary.request_count,
            1,
        )

        self.assertEqual(
            summary.total_tokens,
            10,
        )

    def test_failed_requests_counted(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="gemini",
                success=False,
                total_tokens=0,
                error_type="ServerError",
            )
        )

        summary = self.ledger.summarize()

        self.assertEqual(
            summary.failed_requests,
            1,
        )

        self.assertEqual(
            summary.successful_requests,
            0,
        )

    def test_record_limit_is_bounded(
        self,
    ) -> None:
        for index in range(5):
            self.ledger.append(
                self._record(
                    provider="openai",
                    total_tokens=index,
                )
            )

        records = self.ledger.list_all()

        self.assertEqual(
            len(records),
            3,
        )

        self.assertEqual(
            [
                record.total_tokens
                for record in records
            ],
            [2, 3, 4],
        )

    def test_summary_by_provider(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="openai",
                total_tokens=10,
            )
        )

        self.ledger.append(
            self._record(
                provider="gemini",
                total_tokens=20,
            )
        )

        summaries = (
            self.ledger
            .summarize_by_provider()
        )

        self.assertEqual(
            summaries["openai"].total_tokens,
            10,
        )

        self.assertEqual(
            summaries["gemini"].total_tokens,
            20,
        )

    def test_since_filter(
        self,
    ) -> None:
        old_record = self._record(
            provider="openai",
            total_tokens=10,
        )

        current_record = (
            TokenUsageRecord.create(
                provider="openai",
                model="test-model",
                success=True,
                total_tokens=20,
            )
        )

        old_payload = {
            **old_record.__dict__
        } if hasattr(
            old_record,
            "__dict__",
        ) else None

        self.ledger.append(
            TokenUsageRecord(
                record_id="old",
                timestamp=(
                    datetime.now(timezone.utc)
                    - timedelta(days=2)
                ).isoformat(),
                provider="openai",
                model="test-model",
                success=True,
                input_tokens=0,
                output_tokens=0,
                total_tokens=10,
            )
        )

        self.ledger.append(
            current_record
        )

        summary = self.ledger.summarize(
            since=(
                datetime.now(timezone.utc)
                - timedelta(hours=1)
            )
        )

        self.assertEqual(
            summary.request_count,
            1,
        )

        self.assertEqual(
            summary.total_tokens,
            20,
        )

        self.assertIsNone(old_payload)

    def test_clear(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="openai",
                total_tokens=10,
            )
        )

        self.ledger.clear()

        self.assertEqual(
            self.ledger.list_all(),
            [],
        )

    def test_storage_does_not_contain_prompts(
        self,
    ) -> None:
        self.ledger.append(
            self._record(
                provider="openai",
                total_tokens=10,
            )
        )

        payload = json.loads(
            self.path.read_text(
                encoding="utf-8"
            )
        )

        serialized = json.dumps(payload)

        self.assertNotIn(
            "prompt",
            serialized.lower(),
        )

        self.assertNotIn(
            "response_text",
            serialized,
        )

    @staticmethod
    def _record(
        *,
        provider: str,
        success: bool = True,
        input_tokens: int = 0,
        output_tokens: int = 0,
        total_tokens: int = 0,
        cached_input_tokens: int = 0,
        reasoning_tokens: int = 0,
        tool_tokens: int = 0,
        latency_ms: int = 0,
        error_type: str | None = None,
    ) -> TokenUsageRecord:
        return TokenUsageRecord.create(
            provider=provider,
            model="test-model",
            success=success,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=(
                cached_input_tokens
            ),
            reasoning_tokens=(
                reasoning_tokens
            ),
            tool_tokens=tool_tokens,
            latency_ms=latency_ms,
            error_type=error_type,
        )


if __name__ == "__main__":
    unittest.main()
