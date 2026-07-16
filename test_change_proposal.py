from __future__ import annotations

import json

from core.execution.change_proposal import (
    ChangeProposalError,
    ChangeProposalParser,
    FileOperation,
)


parser = ChangeProposalParser(
    max_files=5,
    max_file_characters=20_000,
    max_total_characters=50_000,
    max_test_commands=5,
)

valid_payload = {
    "summary": "Add calculator multiplication support.",
    "changes": [
        {
            "path": "app/calculator.py",
            "operation": "update",
            "content": (
                "def add(a: int, b: int) -> int:\n"
                "    return a + b\n\n"
                "def multiply(a: int, b: int) -> int:\n"
                "    return a * b\n"
            ),
        },
        {
            "path": "test_calculator.py",
            "operation": "create",
            "content": (
                "from app.calculator import multiply\n\n"
                "assert multiply(4, 5) == 20\n"
            ),
        },
    ],
    "test_commands": [
        ["python", "test_calculator.py"],
    ],
}

raw_result = parser.parse(
    json.dumps(valid_payload)
)

assert raw_result.summary == (
    "Add calculator multiplication support."
)
assert len(raw_result.changes) == 2

assert raw_result.changes[0].path == (
    "app/calculator.py"
)
assert raw_result.changes[0].operation == (
    FileOperation.UPDATE
)
assert "def multiply" in (
    raw_result.changes[0].content
)

assert raw_result.changes[1].operation == (
    FileOperation.CREATE
)

assert raw_result.test_commands == (
    ("python", "test_calculator.py"),
)

fenced_result = parser.parse(
    "Worker response:\n```json\n"
    + json.dumps(valid_payload)
    + "\n```"
)

assert fenced_result == raw_result

contract = parser.render_worker_contract()

assert '"changes"' in contract
assert '"test_commands"' in contract
assert "complete final file content" in contract

duplicate_payload = dict(valid_payload)
duplicate_payload["changes"] = [
    valid_payload["changes"][0],
    valid_payload["changes"][0],
]

try:
    parser.parse(
        json.dumps(duplicate_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Duplicate file paths must be rejected."
    )

unsafe_path_payload = {
    "summary": "Unsafe traversal",
    "changes": [
        {
            "path": "../outside.py",
            "operation": "create",
            "content": "unsafe = True\n",
        },
    ],
    "test_commands": [],
}

try:
    parser.parse(
        json.dumps(unsafe_path_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Path traversal must be rejected."
    )

secret_payload = {
    "summary": "Unsafe secret",
    "changes": [
        {
            "path": ".env",
            "operation": "update",
            "content": "SECRET=value\n",
        },
    ],
    "test_commands": [],
}

try:
    parser.parse(
        json.dumps(secret_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Environment files must be rejected."
    )

key_payload = {
    "summary": "Unsafe key",
    "changes": [
        {
            "path": "keys/private.pem",
            "operation": "create",
            "content": "PRIVATE KEY\n",
        },
    ],
    "test_commands": [],
}

try:
    parser.parse(
        json.dumps(key_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Private key files must be rejected."
    )

unsafe_command_payload = {
    "summary": "Unsafe command",
    "changes": [
        {
            "path": "app/service.py",
            "operation": "create",
            "content": "value = True\n",
        },
    ],
    "test_commands": [
        ["python", "-c", "print('unsafe')"],
    ],
}

try:
    parser.parse(
        json.dumps(unsafe_command_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Inline Python commands must be rejected."
    )

shell_command_payload = {
    "summary": "Unsafe shell command",
    "changes": [
        {
            "path": "app/service.py",
            "operation": "create",
            "content": "value = True\n",
        },
    ],
    "test_commands": [
        ["python", "test_service.py", "&&", "rm", "-rf", "/"],
    ],
}

try:
    parser.parse(
        json.dumps(shell_command_payload)
    )
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Shell operators must be rejected."
    )

try:
    parser.parse("This is not JSON.")
except ChangeProposalError:
    pass
else:
    raise AssertionError(
        "Non-JSON worker output must be rejected."
    )

print("Change proposal parser passed")
