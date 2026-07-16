from __future__ import annotations

import unittest
from pathlib import Path


class DiscordSystemdServiceTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.service_path = Path(
            "deploy/systemd/"
            "atlas-lite-discord.service"
        )

        self.content = (
            self.service_path.read_text(
                encoding="utf-8"
            )
        )

    def test_service_file_exists(
        self,
    ) -> None:
        self.assertTrue(
            self.service_path.is_file()
        )

    def test_service_runs_as_ubuntu(
        self,
    ) -> None:
        self.assertIn(
            "User=ubuntu",
            self.content,
        )
        self.assertIn(
            "Group=ubuntu",
            self.content,
        )

    def test_service_uses_project_directory(
        self,
    ) -> None:
        self.assertIn(
            (
                "WorkingDirectory="
                "/home/ubuntu/atlas-lite"
            ),
            self.content,
        )

    def test_service_uses_project_environment(
        self,
    ) -> None:
        self.assertIn(
            (
                "EnvironmentFile="
                "/home/ubuntu/atlas-lite/.env"
            ),
            self.content,
        )

    def test_service_uses_virtual_environment(
        self,
    ) -> None:
        self.assertIn(
            (
                "ExecStart="
                "/home/ubuntu/atlas-lite/"
                "venv/bin/python "
                "/home/ubuntu/atlas-lite/"
                "run_discord_bot.py"
            ),
            self.content,
        )

    def test_service_requires_runtime(
        self,
    ) -> None:
        self.assertIn(
            (
                "Requires="
                "atlas-lite-runtime.service"
            ),
            self.content,
        )
        self.assertIn(
            (
                "After=network-online.target "
                "atlas-lite-runtime.service"
            ),
            self.content,
        )

    def test_service_restarts_automatically(
        self,
    ) -> None:
        self.assertIn(
            "Restart=always",
            self.content,
        )
        self.assertIn(
            "RestartSec=15",
            self.content,
        )

    def test_service_is_boot_enabled(
        self,
    ) -> None:
        self.assertIn(
            "WantedBy=multi-user.target",
            self.content,
        )


if __name__ == "__main__":
    unittest.main()
