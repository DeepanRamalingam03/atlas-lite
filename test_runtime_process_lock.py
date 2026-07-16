from __future__ import annotations

import multiprocessing
import os
import shutil
import time
import unittest
from pathlib import Path

from core.orchestration.runtime_lock import (
    RuntimeLockError,
    RuntimeProcessLock,
)


def hold_lock(
    lock_path: str,
    ready_queue: multiprocessing.Queue,
    release_queue: multiprocessing.Queue,
) -> None:
    lock = RuntimeProcessLock(
        lock_path=lock_path
    )

    owner = lock.acquire()

    ready_queue.put(
        {
            "pid": owner.pid,
            "hostname": owner.hostname,
            "acquired_at": owner.acquired_at,
            "lock_path": owner.lock_path,
        }
    )

    release_queue.get(
        timeout=10
    )

    lock.release()


class RuntimeProcessLockTest(
    unittest.TestCase
):
    def setUp(self) -> None:
        self.root = Path(
            ".atlas_runtime_lock_test"
        )

        if self.root.exists():
            shutil.rmtree(self.root)

        self.root.mkdir(
            parents=True
        )

        self.lock_path = (
            self.root / "atlas.lock"
        )

    def tearDown(self) -> None:
        if self.root.exists():
            shutil.rmtree(self.root)

    def test_acquire_and_release(
        self,
    ) -> None:
        lock = RuntimeProcessLock(
            self.lock_path
        )

        owner = lock.acquire()

        self.assertTrue(
            lock.acquired
        )
        self.assertEqual(
            owner.pid,
            os.getpid(),
        )
        self.assertEqual(
            lock.owner,
            owner,
        )

        stored_owner = lock.read_owner()

        self.assertIsNotNone(
            stored_owner
        )
        self.assertEqual(
            stored_owner.pid,
            os.getpid(),
        )

        lock.release()

        self.assertFalse(
            lock.acquired
        )
        self.assertIsNone(
            lock.owner
        )
        self.assertIsNone(
            lock.read_owner()
        )

    def test_context_manager_releases_lock(
        self,
    ) -> None:
        lock = RuntimeProcessLock(
            self.lock_path
        )

        with lock as acquired_lock:
            self.assertIs(
                acquired_lock,
                lock,
            )
            self.assertTrue(
                lock.acquired
            )

        self.assertFalse(
            lock.acquired
        )

        second_lock = RuntimeProcessLock(
            self.lock_path
        )

        second_lock.acquire()
        second_lock.release()

    def test_same_instance_cannot_acquire_twice(
        self,
    ) -> None:
        lock = RuntimeProcessLock(
            self.lock_path
        )

        lock.acquire()

        with self.assertRaises(
            RuntimeLockError
        ):
            lock.acquire()

        lock.release()

    def test_second_process_is_blocked(
        self,
    ) -> None:
        context = multiprocessing.get_context(
            "fork"
        )

        ready_queue = context.Queue()
        release_queue = context.Queue()

        process = context.Process(
            target=hold_lock,
            args=(
                str(self.lock_path),
                ready_queue,
                release_queue,
            ),
        )

        process.start()

        owner_payload = ready_queue.get(
            timeout=10
        )

        self.assertGreater(
            owner_payload["pid"],
            0,
        )

        competing_lock = RuntimeProcessLock(
            self.lock_path
        )

        with self.assertRaises(
            RuntimeLockError
        ) as raised:
            competing_lock.acquire()

        self.assertIn(
            f"pid={owner_payload['pid']}",
            str(raised.exception),
        )

        release_queue.put(
            "release"
        )

        process.join(
            timeout=10
        )

        self.assertFalse(
            process.is_alive()
        )
        self.assertEqual(
            process.exitcode,
            0,
        )

        time.sleep(0.05)

        competing_lock.acquire()
        competing_lock.release()

    def test_release_is_idempotent(
        self,
    ) -> None:
        lock = RuntimeProcessLock(
            self.lock_path
        )

        lock.release()
        lock.acquire()
        lock.release()
        lock.release()

        self.assertFalse(
            lock.acquired
        )

    def test_corrupt_owner_file_is_safe(
        self,
    ) -> None:
        self.lock_path.write_text(
            "invalid-json",
            encoding="utf-8",
        )

        lock = RuntimeProcessLock(
            self.lock_path
        )

        self.assertIsNone(
            lock.read_owner()
        )

        lock.acquire()

        self.assertIsNotNone(
            lock.read_owner()
        )

        lock.release()


if __name__ == "__main__":
    unittest.main()
