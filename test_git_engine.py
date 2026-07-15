from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from git_tools.engine import GitEngine


repository_root = Path(".atlas_git_test_repo")


def run_git(*args: str) -> None:
    completed = subprocess.run(
        ["git", *args],
        cwd=repository_root,
        capture_output=True,
        text=True,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            completed.stdout + completed.stderr
        )


if repository_root.exists():
    shutil.rmtree(repository_root)

repository_root.mkdir(parents=True)

run_git("init")
run_git("config", "user.name", "Atlas Test")
run_git(
    "config",
    "user.email",
    "atlas-test@example.com",
)

(repository_root / "initial.txt").write_text(
    "initial\n",
    encoding="utf-8",
)

run_git("add", "initial.txt")
run_git("commit", "-m", "Initial test commit")

engine = GitEngine(
    repository_root=repository_root,
    timeout_seconds=30,
)

clean_status = engine.status()

assert clean_status.success is True
assert clean_status.stdout.strip() == ""

(repository_root / "generated.py").write_text(
    "VALUE = 42\n",
    encoding="utf-8",
)

changed_files = engine.changed_files()

assert "generated.py" in changed_files

publish_result = engine.publish(
    paths=["generated.py"],
    commit_message="Add generated module",
    push=False,
)

assert publish_result.success is True
assert publish_result.committed is True
assert publish_result.pushed is False
assert publish_result.commit_result is not None
assert publish_result.commit_result.success is True

final_status = engine.status()

assert final_status.success is True
assert final_status.stdout.strip() == ""

try:
    engine.add([".env"])
except PermissionError:
    pass
else:
    raise AssertionError(
        "Protected .env path was not rejected."
    )

shutil.rmtree(repository_root)

print("Git engine passed")
