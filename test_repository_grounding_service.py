from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from services.project.repository_grounding_service import (
    RepositoryGroundingError,
    RepositoryGroundingService,
)


class FakeContextBuilder:
    def build(
        self,
        project_root: str | Path,
    ) -> str:
        return (
            "ATLAS CONSTITUTION\n"
            "PROJECT FILE STRUCTURE\n"
            "main.py\n"
            "test_main.py\n"
            "PYTHON PROJECT INDEX\n"
            "function: run"
        )


class FakeRelevantContextService:
    def build(
        self,
        request: str,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            rendered_context=(
                "RELEVANT PROJECT FILE CONTEXT\n"
                "FILE: main.py\n"
                "CONTENT\n"
                "def run() -> str:\n"
                "    return 'ok'\n"
            )
        )


class EmptyContextBuilder:
    def build(
        self,
        project_root: str | Path,
    ) -> str:
        return ""


class RepositoryGroundingServiceTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_repository_grounding_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self._git(
            "init",
            "-b",
            "main",
        )

        self._git(
            "config",
            "user.name",
            "Atlas Test",
        )

        self._git(
            "config",
            "user.email",
            "atlas-test@example.com",
        )

        (
            self.root / "main.py"
        ).write_text(
            (
                "def run() -> str:\n"
                "    return 'ok'\n"
            ),
            encoding="utf-8",
        )

        (
            self.root / "test_main.py"
        ).write_text(
            (
                "from main import run\n\n"
                "def test_run() -> None:\n"
                "    assert run() == 'ok'\n"
            ),
            encoding="utf-8",
        )

        (
            self.root / "README.md"
        ).write_text(
            "# Test Repository\n",
            encoding="utf-8",
        )

        self._git(
            "add",
            "main.py",
            "test_main.py",
            "README.md",
        )

        self._git(
            "commit",
            "-m",
            "Initial repository",
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_build_uses_git_tracked_files(
        self,
    ) -> None:
        grounding = (
            self._service().build(
                "Inspect the repository."
            )
        )

        self.assertEqual(
            grounding.tracked_file_count,
            3,
        )

        self.assertEqual(
            grounding.python_file_count,
            2,
        )

        self.assertEqual(
            grounding.test_file_count,
            1,
        )

        self.assertIn(
            "main.py",
            grounding.tracked_files,
        )

        self.assertIn(
            "test_main.py",
            grounding.test_files,
        )

    def test_untracked_files_are_not_facts(
        self,
    ) -> None:
        (
            self.root / "untracked.py"
        ).write_text(
            "value = 1\n",
            encoding="utf-8",
        )

        grounding = (
            self._service().build(
                "Inspect tracked files."
            )
        )

        self.assertNotIn(
            "untracked.py",
            grounding.tracked_files,
        )

        self.assertEqual(
            grounding.python_file_count,
            2,
        )

    def test_rendered_context_contains_counts(
        self,
    ) -> None:
        grounding = (
            self._service().build(
                "Verify Python implementation."
            )
        )

        self.assertIn(
            "Tracked file count: 3",
            grounding.rendered_context,
        )

        self.assertIn(
            "Tracked Python file count: 2",
            grounding.rendered_context,
        )

        self.assertIn(
            "Tracked test file count: 1",
            grounding.rendered_context,
        )

        self.assertIn(
            "implemented Python repository",
            grounding.rendered_context,
        )

    def test_rendered_context_distinguishes_staging(
        self,
    ) -> None:
        grounding = (
            self._service().build(
                "Create documentation."
            )
        )

        self.assertIn(
            (
                "temporary staging "
                "workspace"
            ),
            grounding.rendered_context,
        )

        self.assertIn(
            (
                "does not mean the "
                "repository has no Python code"
            ),
            grounding.rendered_context,
        )

    def test_rendered_context_includes_project_index(
        self,
    ) -> None:
        grounding = (
            self._service().build(
                "Inspect symbols."
            )
        )

        self.assertIn(
            "PROJECT FILE STRUCTURE",
            grounding.rendered_context,
        )

        self.assertIn(
            "function: run",
            grounding.rendered_context,
        )

    def test_rendered_context_includes_relevant_content(
        self,
    ) -> None:
        grounding = (
            self._service().build(
                "Inspect main.py."
            )
        )

        self.assertIn(
            "FILE: main.py",
            grounding.rendered_context,
        )

        self.assertIn(
            "def run() -> str:",
            grounding.rendered_context,
        )

    def test_empty_request_is_rejected(
        self,
    ) -> None:
        with self.assertRaises(
            ValueError
        ):
            self._service().build("   ")

    def test_non_git_directory_is_rejected(
        self,
    ) -> None:
        plain_root = (
            self.root / "plain"
        )

        plain_root.mkdir()

        service = RepositoryGroundingService(
            project_root=plain_root,
            context_builder=(
                FakeContextBuilder()
            ),
            relevant_context_service=(
                FakeRelevantContextService()
            ),
        )

        with self.assertRaises(
            RepositoryGroundingError
        ):
            service.build(
                "Inspect repository."
            )

    def test_empty_context_is_rejected(
        self,
    ) -> None:
        service = RepositoryGroundingService(
            project_root=self.root,
            context_builder=(
                EmptyContextBuilder()
            ),
            relevant_context_service=(
                FakeRelevantContextService()
            ),
        )

        with self.assertRaises(
            RepositoryGroundingError
        ):
            service.build(
                "Inspect repository."
            )

    def test_manifest_limit_is_bounded(
        self,
    ) -> None:
        service = RepositoryGroundingService(
            project_root=self.root,
            context_builder=(
                FakeContextBuilder()
            ),
            relevant_context_service=(
                FakeRelevantContextService()
            ),
            max_manifest_files=1,
        )

        grounding = service.build(
            "Inspect repository."
        )

        self.assertIn(
            "additional tracked files omitted",
            grounding.rendered_context,
        )

    def _service(
        self,
    ) -> RepositoryGroundingService:
        return RepositoryGroundingService(
            project_root=self.root,
            context_builder=(
                FakeContextBuilder()
            ),
            relevant_context_service=(
                FakeRelevantContextService()
            ),
        )

    def _git(
        self,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [
                "git",
                *arguments,
            ],
            cwd=self.root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

        if completed.returncode != 0:
            raise RuntimeError(
                "Git command failed:\n"
                f"git {' '.join(arguments)}\n"
                f"{completed.stdout}\n"
                f"{completed.stderr}"
            )

        return completed


if __name__ == "__main__":
    unittest.main()
