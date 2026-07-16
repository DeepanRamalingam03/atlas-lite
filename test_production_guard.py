from __future__ import annotations

import multiprocessing
import shutil
import subprocess
import unittest
from pathlib import Path
from types import SimpleNamespace

from core.orchestration.production_guard import (
    DiskPressureGuard,
    LockedReleaseCoordinator,
    ProductionGuardError,
    ProductionPreflight,
    RepositoryLockError,
    RepositoryOperationLock,
)


def hold_lock(
    lock_path: str,
    ready_queue: multiprocessing.Queue,
    release_queue: multiprocessing.Queue,
) -> None:
    lock = RepositoryOperationLock(
        lock_path,
        operation="test-owner",
    )

    owner = lock.acquire()
    ready_queue.put(owner.pid)

    release_queue.get(timeout=10)
    lock.release()


class FakeReleaseCoordinator:
    def __init__(self) -> None:
        self.calls = 0

    def preview(self) -> str:
        return "preview"

    def release(
        self,
        commit_message: str,
        push: bool = False,
        remote: str = "origin",
        branch: str = "main",
        diff_plan=None,
    ):
        self.calls += 1

        return SimpleNamespace(
            success=True,
            error=None,
            commit_message=commit_message,
        )


class ProductionGuardTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_production_guard_test"
        ).resolve()

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(parents=True)

        self.repository = (
            self.root / "repository"
        )

        self.repository.mkdir()

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
            self.repository / ".gitignore"
        ).write_text(
            ".atlas_data/\n",
            encoding="utf-8",
        )

        (
            self.repository / "README.md"
        ).write_text(
            "# Atlas Test\n",
            encoding="utf-8",
        )

        self._git(
            "add",
            ".gitignore",
            "README.md",
        )

        self._git(
            "commit",
            "-m",
            "Initial test repository",
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_disk_guard_accepts_safe_capacity(
        self,
    ) -> None:
        usage = shutil._ntuple_diskusage(
            total=1000,
            used=500,
            free=500,
        )

        guard = DiskPressureGuard(
            self.repository,
            minimum_free_bytes=100,
            minimum_free_percent=10,
            usage_provider=lambda path: usage,
        )

        status = guard.require_safe()

        self.assertTrue(status.safe)
        self.assertEqual(
            status.free_percent,
            50.0,
        )

    def test_disk_guard_blocks_low_bytes(
        self,
    ) -> None:
        usage = shutil._ntuple_diskusage(
            total=1000,
            used=950,
            free=50,
        )

        guard = DiskPressureGuard(
            self.repository,
            minimum_free_bytes=100,
            minimum_free_percent=1,
            usage_provider=lambda path: usage,
        )

        with self.assertRaises(
            ProductionGuardError
        ):
            guard.require_safe()

    def test_disk_guard_blocks_low_percentage(
        self,
    ) -> None:
        usage = shutil._ntuple_diskusage(
            total=100_000,
            used=99_000,
            free=1_000,
        )

        guard = DiskPressureGuard(
            self.repository,
            minimum_free_bytes=100,
            minimum_free_percent=5,
            usage_provider=lambda path: usage,
        )

        with self.assertRaises(
            ProductionGuardError
        ):
            guard.require_safe()

    def test_clean_preflight_passes(
        self,
    ) -> None:
        result = (
            self._preflight()
            .require_safe()
        )

        self.assertTrue(result.safe)
        self.assertTrue(
            result.repository_clean
        )
        self.assertEqual(
            result.branch,
            "main",
        )

    def test_ignored_runtime_state_does_not_block(
        self,
    ) -> None:
        runtime_file = (
            self.repository
            / ".atlas_data"
            / "heartbeat.json"
        )

        runtime_file.parent.mkdir()
        runtime_file.write_text(
            "{}",
            encoding="utf-8",
        )

        result = (
            self._preflight()
            .require_safe()
        )

        self.assertTrue(result.safe)

    def test_untracked_source_file_does_not_block_pre_apply(
        self,
    ) -> None:
        (
            self.repository
            / "generated_file.py"
        ).write_text(
            "value = 1\n",
            encoding="utf-8",
        )

        result = (
            self._preflight()
            .require_safe()
        )

        self.assertTrue(result.safe)

    def test_tracked_change_blocks_preflight(
        self,
    ) -> None:
        (
            self.repository / "README.md"
        ).write_text(
            "# Modified\n",
            encoding="utf-8",
        )

        with self.assertRaises(
            ProductionGuardError
        ):
            self._preflight().require_safe()

    def test_wrong_branch_blocks_preflight(
        self,
    ) -> None:
        self._git(
            "checkout",
            "-b",
            "other",
        )

        with self.assertRaises(
            ProductionGuardError
        ):
            self._preflight().require_safe()

    def test_same_lock_instance_cannot_acquire_twice(
        self,
    ) -> None:
        lock = RepositoryOperationLock(
            self.root / "same.lock"
        )

        lock.acquire()

        with self.assertRaises(
            RepositoryLockError
        ):
            lock.acquire()

        lock.release()

    def test_lock_release_is_idempotent(
        self,
    ) -> None:
        lock = RepositoryOperationLock(
            self.root / "release.lock"
        )

        lock.acquire()
        lock.release()
        lock.release()

        self.assertFalse(lock.acquired)

    def test_second_process_is_blocked(
        self,
    ) -> None:
        context = (
            multiprocessing
            .get_context("fork")
        )

        ready_queue = context.Queue()
        release_queue = context.Queue()

        lock_path = (
            self.root / "shared.lock"
        )

        process = context.Process(
            target=hold_lock,
            args=(
                str(lock_path),
                ready_queue,
                release_queue,
            ),
        )

        process.start()

        owner_pid = ready_queue.get(
            timeout=10
        )

        competing_lock = (
            RepositoryOperationLock(
                lock_path,
                operation="competitor",
            )
        )

        with self.assertRaises(
            RepositoryLockError
        ) as raised:
            competing_lock.acquire()

        self.assertIn(
            f"pid={owner_pid}",
            str(raised.exception),
        )

        release_queue.put("release")
        process.join(timeout=10)

        self.assertEqual(
            process.exitcode,
            0,
        )

        competing_lock.acquire()
        competing_lock.release()

    def test_locked_coordinator_delegates_release(
        self,
    ) -> None:
        delegate = FakeReleaseCoordinator()

        coordinator = (
            LockedReleaseCoordinator(
                delegate=delegate,
                operation_lock=(
                    RepositoryOperationLock(
                        self.root
                        / "coordinator.lock"
                    )
                ),
                preflight=self._preflight(),
            )
        )

        result = coordinator.release(
            commit_message="Safe release",
            push=False,
        )

        self.assertTrue(result.success)
        self.assertEqual(
            delegate.calls,
            1,
        )
        self.assertFalse(
            coordinator
            .operation_lock
            .acquired
        )

    def test_locked_coordinator_does_not_delegate_when_unsafe(
        self,
    ) -> None:
        delegate = FakeReleaseCoordinator()

        (
            self.repository / "README.md"
        ).write_text(
            "# Dirty\n",
            encoding="utf-8",
        )

        coordinator = (
            LockedReleaseCoordinator(
                delegate=delegate,
                operation_lock=(
                    RepositoryOperationLock(
                        self.root
                        / "blocked.lock"
                    )
                ),
                preflight=self._preflight(),
            )
        )

        with self.assertRaises(
            ProductionGuardError
        ):
            coordinator.release(
                commit_message="Blocked release",
            )

        self.assertEqual(
            delegate.calls,
            0,
        )
        self.assertFalse(
            coordinator
            .operation_lock
            .acquired
        )

    def _preflight(
        self,
    ) -> ProductionPreflight:
        usage = shutil._ntuple_diskusage(
            total=1000,
            used=500,
            free=500,
        )

        return ProductionPreflight(
            repository_root=self.repository,
            disk_guard=DiskPressureGuard(
                self.repository,
                minimum_free_bytes=100,
                minimum_free_percent=10,
                usage_provider=lambda path: usage,
            ),
            expected_branch="main",
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
            cwd=self.repository,
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
