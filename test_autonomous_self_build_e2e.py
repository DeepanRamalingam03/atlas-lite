from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from apply.engine import TransactionalApplyEngine
from core.orchestration.autonomy_policy import (
    AutonomyPolicy,
)
from core.orchestration.continuous_loop import (
    ContinuousOrchestrator,
)
from core.orchestration.recovery_manager import (
    WorkflowRecoveryManager,
)
from core.orchestration.roadmap import (
    RoadmapTaskSelector,
    RoadmapTaskStatus,
    RoadmapTaskStore,
)
from core.orchestration.runtime_lock import (
    RuntimeProcessLock,
)
from core.orchestration.runtime_service import (
    ContinuousRuntimeService,
    RuntimeCycleStatus,
)
from core.orchestration.state_store import (
    WorkflowStateStore,
)
from git_tools.engine import GitEngine
from orchestrator.pipeline import AtlasPipeline
from release.coordinator import ReleaseCoordinator
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewParser
from services.worker_output_parser import (
    WorkerOutputParser,
)
from testing.runner import StagingTestRunner
from workspace.diff_engine import WorkspaceDiffEngine
from workspace.writer import WorkspaceWriter


class FakeManager:
    def create_worker_prompt(
        self,
        goal: str,
    ) -> str:
        return (
            "Create generated_math.py containing an add function "
            "and create test_generated_math.py with executable "
            "assertions for the add function."
        )

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        return (
            "DECISION: APPROVED\n\n"
            "REASON:\n"
            "The staged implementation is complete and validated.\n\n"
            "FIX_INSTRUCTION:\n"
            "NONE"
        )


class FakeWorker:
    def execute(
        self,
        instruction: str,
    ) -> str:
        payload = {
            "summary": (
                "Added a generated math module and its test."
            ),
            "files": [
                {
                    "path": "generated_math.py",
                    "content": (
                        "from __future__ import annotations\n\n"
                        "\n"
                        "def add(left: int, right: int) -> int:\n"
                        "    return left + right\n"
                    ),
                },
                {
                    "path": "test_generated_math.py",
                    "content": (
                        "from generated_math import add\n\n"
                        "\n"
                        "assert add(2, 3) == 5\n"
                        "assert add(-2, 2) == 0\n"
                        "\n"
                        "print('Generated math test passed')\n"
                    ),
                },
            ],
        }

        return json.dumps(payload)


class AutonomousSelfBuildEndToEndTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_self_build_e2e_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.project_root = (
            self.root / "project"
        )
        self.staging_root = (
            self.root / "staging"
        )
        self.backup_root = (
            self.root / "backups"
        )
        self.data_root = (
            self.root / "data"
        )

        self.project_root.mkdir(
            parents=True
        )

        self._run_git(
            "init",
            "-b",
            "main",
        )
        self._run_git(
            "config",
            "user.name",
            "Atlas Test",
        )
        self._run_git(
            "config",
            "user.email",
            "atlas-test@example.com",
        )

        (
            self.project_root / ".gitignore"
        ).write_text(
            "__pycache__/\n"
            "*.pyc\n"
            "*.pyo\n",
            encoding="utf-8",
        )

        (
            self.project_root / "README.md"
        ).write_text(
            "# Atlas Self Build Test\n",
            encoding="utf-8",
        )

        self._run_git(
            "add",
            ".gitignore",
            "README.md",
        )
        self._run_git(
            "commit",
            "-m",
            "Initial test repository",
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_complete_autonomous_self_build_flow(
        self,
    ) -> None:
        pipeline = AtlasPipeline(
            manager=FakeManager(),
            worker=FakeWorker(),
            prompt_builder=PromptBuilder(),
            parser=WorkerOutputParser(),
            review_parser=ReviewParser(),
            workspace_writer=WorkspaceWriter(
                staging_root=self.staging_root,
            ),
            test_runner=StagingTestRunner(
                staging_root=self.staging_root,
                timeout_seconds=30,
            ),
            max_iterations=2,
        )

        git_engine = GitEngine(
            repository_root=self.project_root,
            timeout_seconds=30,
        )

        diff_engine = WorkspaceDiffEngine(
            project_root=self.project_root,
            staging_root=self.staging_root,
        )

        apply_engine = TransactionalApplyEngine(
            project_root=self.project_root,
            staging_root=self.staging_root,
            backup_root=self.backup_root,
        )

        release_coordinator = ReleaseCoordinator(
            project_root=self.project_root,
            staging_root=self.staging_root,
            git_engine=git_engine,
            apply_engine=apply_engine,
            diff_engine=diff_engine,
        )

        workflow_store = WorkflowStateStore(
            storage_path=(
                self.data_root
                / "workflows.json"
            ),
        )

        roadmap_store = RoadmapTaskStore(
            storage_path=(
                self.data_root
                / "roadmap.json"
            ),
        )

        orchestrator = ContinuousOrchestrator(
            pipeline=pipeline,
            release_coordinator=release_coordinator,
            workflow_store=workflow_store,
            autonomy_policy=AutonomyPolicy(
                development_branches={
                    "main",
                },
            ),
            remote="origin",
            branch="main",
            push=False,
        )

        recovery_manager = WorkflowRecoveryManager(
            orchestrator=orchestrator,
            workflow_store=workflow_store,
        )

        runtime_service = ContinuousRuntimeService(
            roadmap_store=roadmap_store,
            roadmap_selector=RoadmapTaskSelector(
                roadmap_store
            ),
            orchestrator=orchestrator,
            recovery_manager=recovery_manager,
            process_lock=RuntimeProcessLock(
                self.data_root / "runtime.lock"
            ),
            user_id=100,
            idle_seconds=0,
        )

        roadmap_store.create(
            title="Autonomous self-build validation",
            goal=(
                "Create and validate a generated math module "
                "with a test, apply it transactionally, "
                "and commit the result."
            ),
            priority=1,
            source="bootstrap-e2e-test",
            task_id="self-build-e2e",
        )

        cycle_result = runtime_service.run_once()

        self.assertEqual(
            cycle_result.status,
            RuntimeCycleStatus.COMPLETED,
        )
        self.assertIsNotNone(
            cycle_result.workflow_result
        )
        self.assertTrue(
            cycle_result.workflow_result.completed
        )

        roadmap_task = roadmap_store.require(
            "self-build-e2e"
        )

        self.assertEqual(
            roadmap_task.status,
            RoadmapTaskStatus.COMPLETED,
        )

        generated_module = (
            self.project_root
            / "generated_math.py"
        )

        generated_test = (
            self.project_root
            / "test_generated_math.py"
        )

        self.assertTrue(
            generated_module.is_file()
        )
        self.assertTrue(
            generated_test.is_file()
        )

        test_environment = os.environ.copy()
        test_environment[
            "PYTHONDONTWRITEBYTECODE"
        ] = "1"

        test_process = subprocess.run(
            [
                sys.executable,
                str(generated_test),
            ],
            cwd=self.project_root,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
            env=test_environment,
        )

        self.assertEqual(
            test_process.returncode,
            0,
            msg=(
                test_process.stdout
                + "\n"
                + test_process.stderr
            ),
        )
        self.assertIn(
            "Generated math test passed",
            test_process.stdout,
        )

        git_status = self._run_git(
            "status",
            "--porcelain",
        )

        self.assertEqual(
            git_status.stdout.strip(),
            "",
        )

        git_log = self._run_git(
            "log",
            "-1",
            "--pretty=%s",
        )

        self.assertEqual(
            git_log.stdout.strip(),
            (
                "Atlas roadmap - "
                "Autonomous self-build validation"
            ),
        )

        committed_files = self._run_git(
            "show",
            "--name-only",
            "--pretty=",
            "HEAD",
        )

        committed_paths = {
            line.strip()
            for line in committed_files.stdout.splitlines()
            if line.strip()
        }

        self.assertEqual(
            committed_paths,
            {
                "generated_math.py",
                "test_generated_math.py",
            },
        )

        workflows = (
            workflow_store.list_for_user(
                100
            )
        )

        self.assertEqual(
            len(workflows),
            1,
        )
        self.assertEqual(
            workflows[0].status.value,
            "completed",
        )

        idle_result = runtime_service.run_once()

        self.assertEqual(
            idle_result.status,
            RuntimeCycleStatus.IDLE,
        )
        self.assertIn(
            "will not create random work",
            idle_result.message,
        )

    def _run_git(
        self,
        *arguments: str,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [
                "git",
                *arguments,
            ],
            cwd=self.project_root,
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
