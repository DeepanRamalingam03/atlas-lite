from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from apply.engine import (
    TransactionalApplyEngine,
)
from core.orchestration.production_guard import (
    LockedReleaseCoordinator,
)
from core.orchestration.runtime_service import (
    ContinuousRuntimeService,
)
from release.coordinator import (
    ReleaseCoordinator,
)
from run_continuous_runtime import (
    BACKUP_ROOT,
    PROJECT_ROOT,
    STAGING_ROOT,
    boolean_setting,
    build_base_release_coordinator,
    build_release_coordinator,
    non_negative_float,
    positive_integer,
)


class ContinuousRuntimeEntrypointTest(
    unittest.TestCase
):
    def test_positive_integer_default(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {},
            clear=False,
        ):
            os.environ.pop(
                "ATLAS_TEST_INTEGER",
                None,
            )

            self.assertEqual(
                positive_integer(
                    "ATLAS_TEST_INTEGER",
                    5,
                ),
                5,
            )

    def test_positive_integer_rejects_zero(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "ATLAS_TEST_INTEGER": "0",
            },
        ):
            with self.assertRaises(
                RuntimeError
            ):
                positive_integer(
                    "ATLAS_TEST_INTEGER",
                    5,
                )

    def test_non_negative_float(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "ATLAS_TEST_FLOAT": "1.5",
            },
        ):
            self.assertEqual(
                non_negative_float(
                    "ATLAS_TEST_FLOAT",
                    2.0,
                ),
                1.5,
            )

    def test_negative_float_rejected(
        self,
    ) -> None:
        with patch.dict(
            os.environ,
            {
                "ATLAS_TEST_FLOAT": "-1",
            },
        ):
            with self.assertRaises(
                RuntimeError
            ):
                non_negative_float(
                    "ATLAS_TEST_FLOAT",
                    2.0,
                )

    def test_boolean_setting(
        self,
    ) -> None:
        for value in (
            "true",
            "1",
            "yes",
            "on",
        ):
            with self.subTest(
                value=value
            ):
                with patch.dict(
                    os.environ,
                    {
                        "ATLAS_TEST_BOOL": value,
                    },
                ):
                    self.assertTrue(
                        boolean_setting(
                            "ATLAS_TEST_BOOL",
                            False,
                        )
                    )

        for value in (
            "false",
            "0",
            "no",
            "off",
        ):
            with self.subTest(
                value=value
            ):
                with patch.dict(
                    os.environ,
                    {
                        "ATLAS_TEST_BOOL": value,
                    },
                ):
                    self.assertFalse(
                        boolean_setting(
                            "ATLAS_TEST_BOOL",
                            True,
                        )
                    )

    def test_base_release_coordinator_builds(
        self,
    ) -> None:
        coordinator = (
            build_base_release_coordinator()
        )

        self.assertIsInstance(
            coordinator,
            ReleaseCoordinator,
        )

        self.assertIsInstance(
            coordinator.apply_engine,
            TransactionalApplyEngine,
        )

        self.assertEqual(
            coordinator.project_root,
            PROJECT_ROOT.resolve(),
        )

        self.assertEqual(
            coordinator.staging_root,
            STAGING_ROOT.resolve(),
        )

        self.assertEqual(
            coordinator.apply_engine.project_root,
            PROJECT_ROOT.resolve(),
        )

        self.assertEqual(
            coordinator.apply_engine.staging_root,
            STAGING_ROOT.resolve(),
        )

        self.assertEqual(
            coordinator.apply_engine.backup_root,
            BACKUP_ROOT.resolve(),
        )

    def test_guarded_release_coordinator_builds(
        self,
    ) -> None:
        coordinator = (
            build_release_coordinator(
                branch="main"
            )
        )

        self.assertIsInstance(
            coordinator,
            LockedReleaseCoordinator,
        )

        self.assertIsInstance(
            coordinator.delegate,
            ReleaseCoordinator,
        )

        self.assertEqual(
            coordinator.preflight.expected_branch,
            "main",
        )

        self.assertFalse(
            coordinator.operation_lock.acquired
        )

    def test_runtime_service_type_available(
        self,
    ) -> None:
        self.assertIsNotNone(
            ContinuousRuntimeService
        )


if __name__ == "__main__":
    unittest.main()
