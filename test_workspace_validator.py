from __future__ import annotations

import shutil
import sys
from pathlib import Path

from core.execution.workspace import (
    SafeWorkspace,
)
from core.execution.workspace_validator import (
    WorkspaceValidationError,
    WorkspaceValidator,
)


test_root = Path(
    ".atlas_workspace_validator_test"
)
project_root = test_root / "project"

if test_root.exists():
    shutil.rmtree(test_root)

(project_root / "app").mkdir(
    parents=True,
)

(project_root / "app" / "__init__.py").write_text(
    "",
    encoding="utf-8",
)

(project_root / "app" / "calculator.py").write_text(
    "def add(a: int, b: int) -> int:\n"
    "    return a + b\n",
    encoding="utf-8",
)

(project_root / "test_calculator.py").write_text(
    "from app.calculator import add\n\n"
    "assert add(2, 3) == 5\n\n"
    "print('Calculator test passed')\n",
    encoding="utf-8",
)

workspace = SafeWorkspace(
    project_root=project_root,
    staging_root=".atlas_staging",
)

workspace.prepare()

workspace.write_text(
    "app/calculator.py",
    (
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n\n"
        "def multiply(a: int, b: int) -> int:\n"
        "    return a * b\n"
    ),
)

workspace.write_text(
    "test_calculator.py",
    (
        "from app.calculator import add, multiply\n\n"
        "assert add(2, 3) == 5\n"
        "assert multiply(4, 5) == 20\n\n"
        "print('Calculator test passed')\n"
    ),
)

validator = WorkspaceValidator(
    workspace=workspace,
    validation_directory=".atlas_validation",
    command_timeout_seconds=30,
)

success_result = validator.validate(
    test_commands=[
        [
            sys.executable,
            "test_calculator.py",
        ],
    ],
)

assert success_result.passed is True
assert success_result.syntax_result.passed is True
assert len(success_result.test_results) == 1
assert success_result.test_results[0].passed is True
assert "Calculator test passed" in (
    success_result.test_results[0].stdout
)
assert "Workspace validation passed." in (
    success_result.summary
)

assert (
    project_root
    / "app"
    / "calculator.py"
).read_text(
    encoding="utf-8"
) == (
    "def add(a: int, b: int) -> int:\n"
    "    return a + b\n"
)

workspace.write_text(
    "app/calculator.py",
    (
        "def broken(:\n"
        "    pass\n"
    ),
)

syntax_failure = validator.validate(
    test_commands=[
        [
            sys.executable,
            "test_calculator.py",
        ],
    ],
)

assert syntax_failure.passed is False
assert syntax_failure.syntax_result.passed is False
assert syntax_failure.test_results == ()
assert "Syntax check: FAILED" in (
    syntax_failure.summary
)

workspace.write_text(
    "app/calculator.py",
    (
        "def add(a: int, b: int) -> int:\n"
        "    return a - b\n"
    ),
)

test_failure = validator.validate(
    test_commands=[
        [
            sys.executable,
            "test_calculator.py",
        ],
    ],
)

assert test_failure.passed is False
assert test_failure.syntax_result.passed is True
assert len(test_failure.test_results) == 1
assert test_failure.test_results[0].passed is False

try:
    validator.validate(
        test_commands=[
            [
                "bash",
                "-c",
                "echo unsafe",
            ],
        ],
    )
except WorkspaceValidationError:
    pass
else:
    raise AssertionError(
        "Unapproved commands must be blocked."
    )

try:
    validator.validate(
        test_commands=[
            [
                sys.executable,
                "-c",
                "print('blocked')",
            ],
        ],
    )
except WorkspaceValidationError:
    pass
else:
    raise AssertionError(
        "Inline Python execution must be blocked."
    )

validator.cleanup()

assert validator.validation_root.exists() is False

shutil.rmtree(test_root)

print("Workspace validator passed")
