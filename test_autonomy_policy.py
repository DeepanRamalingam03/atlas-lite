from __future__ import annotations

import unittest

from core.orchestration.autonomy_policy import (
    AutonomyAction,
    AutonomyPolicy,
    AutonomyRequest,
    DecisionReason,
)


class AutonomyPolicyTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.policy = AutonomyPolicy(
            development_branches={
                "main",
                "atlas-dev",
            }
        )

    def test_routine_change_is_allowed(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.APPLY_CHANGE
                ),
                paths=(
                    "core/orchestration/loop.py",
                    "test_continuous_loop.py",
                ),
            )
        )

        self.assertTrue(
            decision.allowed
        )
        self.assertFalse(
            decision.requires_human
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.ROUTINE_DEVELOPMENT,
        )

    def test_read_operation_is_allowed(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=AutonomyAction.READ,
                paths=(
                    "core/planning/planner.py",
                ),
            )
        )

        self.assertTrue(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.READ_ONLY_OPERATION,
        )

    def test_constitution_path_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.APPLY_CHANGE
                ),
                paths=(
                    "atlas_core/constitution/HANDOFF.md",
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertTrue(
            decision.requires_human
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.CONSTITUTION_CHANGE,
        )

    def test_secret_files_are_blocked(
        self,
    ) -> None:
        paths = (
            ".env",
            ".env.production",
            "config/credentials.json",
            "deploy/service-account.json",
            "certificates/server.pem",
            "certificates/server.key",
        )

        for path in paths:
            with self.subTest(
                path=path
            ):
                decision = (
                    self.policy.evaluate(
                        AutonomyRequest(
                            action=(
                                AutonomyAction
                                .APPLY_CHANGE
                            ),
                            paths=(path,),
                        )
                    )
                )

                self.assertFalse(
                    decision.allowed
                )
                self.assertEqual(
                    decision.reason,
                    DecisionReason.SECRET_REQUIRED,
                )

    def test_path_traversal_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.APPLY_CHANGE
                ),
                paths=(
                    "../outside.py",
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.PROTECTED_PATH,
        )

    def test_protected_paths_are_blocked(
        self,
    ) -> None:
        paths = (
            ".git/config",
            ".ssh/authorized_keys",
            ".aws/credentials",
            "venv/bin/python",
        )

        for path in paths:
            with self.subTest(
                path=path
            ):
                decision = (
                    self.policy.evaluate(
                        AutonomyRequest(
                            action=(
                                AutonomyAction
                                .APPLY_CHANGE
                            ),
                            paths=(path,),
                        )
                    )
                )

                self.assertFalse(
                    decision.allowed
                )
                self.assertEqual(
                    decision.reason,
                    DecisionReason.PROTECTED_PATH,
                )

    def test_approved_branch_push_is_allowed(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.GIT_PUSH
                ),
                branch="main",
                paths=(
                    "core/orchestration/loop.py",
                ),
            )
        )

        self.assertTrue(
            decision.allowed
        )

    def test_unapproved_branch_push_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.GIT_PUSH
                ),
                branch="production",
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.DISALLOWED_BRANCH,
        )

    def test_missing_branch_push_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.GIT_PUSH
                ),
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.DISALLOWED_BRANCH,
        )

    def test_force_push_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action=(
                    AutonomyAction.GIT_PUSH
                ),
                branch="main",
                metadata={
                    "force_push": True,
                },
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.FORCE_PUSH,
        )

    def test_human_controlled_actions_are_blocked(
        self,
    ) -> None:
        expected_reasons = {
            (
                AutonomyAction
                .MODIFY_CONSTITUTION
            ): (
                DecisionReason
                .CONSTITUTION_CHANGE
            ),
            AutonomyAction.ACCESS_SECRET: (
                DecisionReason.SECRET_REQUIRED
            ),
            AutonomyAction.REQUEST_LOGIN: (
                DecisionReason
                .AUTHENTICATION_REQUIRED
            ),
            (
                AutonomyAction
                .DESTRUCTIVE_OPERATION
            ): (
                DecisionReason
                .DESTRUCTIVE_OPERATION
            ),
            (
                AutonomyAction
                .PRODUCTION_DEPLOYMENT
            ): (
                DecisionReason
                .PRODUCTION_OPERATION
            ),
            (
                AutonomyAction
                .CREATE_PAID_RESOURCE
            ): (
                DecisionReason.PAID_RESOURCE
            ),
            (
                AutonomyAction
                .ENABLE_LIVE_TRADING
            ): (
                DecisionReason.LIVE_TRADING
            ),
            (
                AutonomyAction
                .CHANGE_TRADING_RISK
            ): (
                DecisionReason
                .TRADING_RISK_CHANGE
            ),
            (
                AutonomyAction
                .UNRECOVERABLE_BLOCKER
            ): (
                DecisionReason
                .UNRECOVERABLE_BLOCKER
            ),
        }

        for (
            action,
            expected_reason,
        ) in expected_reasons.items():
            with self.subTest(
                action=action
            ):
                decision = (
                    self.policy.evaluate(
                        AutonomyRequest(
                            action=action
                        )
                    )
                )

                self.assertFalse(
                    decision.allowed
                )
                self.assertTrue(
                    decision.requires_human
                )
                self.assertEqual(
                    decision.reason,
                    expected_reason,
                )

    def test_unknown_action_is_blocked(
        self,
    ) -> None:
        decision = self.policy.evaluate(
            AutonomyRequest(
                action="random_work"
            )
        )

        self.assertFalse(
            decision.allowed
        )
        self.assertEqual(
            decision.reason,
            DecisionReason.UNKNOWN_ACTION,
        )

    def test_require_allowed_returns_decision(
        self,
    ) -> None:
        decision = (
            self.policy.require_allowed(
                AutonomyRequest(
                    action=(
                        AutonomyAction.VALIDATE
                    ),
                    paths=(
                        "test_autonomy_policy.py",
                    ),
                )
            )
        )

        self.assertTrue(
            decision.allowed
        )

    def test_require_allowed_raises_for_blocked_request(
        self,
    ) -> None:
        with self.assertRaises(
            PermissionError
        ):
            self.policy.require_allowed(
                AutonomyRequest(
                    action=(
                        AutonomyAction
                        .PRODUCTION_DEPLOYMENT
                    )
                )
            )

    def test_empty_branch_configuration_fails(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            AutonomyPolicy(
                development_branches=()
            )


if __name__ == "__main__":
    unittest.main()
