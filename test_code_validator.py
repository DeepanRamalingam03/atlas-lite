from __future__ import annotations

from services.code_validator import PythonCodeValidator


validator = PythonCodeValidator()

valid_response = (
    "```python\n"
    "def add(a: int, b: int) -> int:\n"
    "    return a + b\n"
    "```\n"
)

valid_result = validator.validate_response(valid_response)

assert valid_result.valid is True
assert valid_result.error is None
assert valid_result.code is not None


invalid_response = (
    "```python\n"
    "def add(a: int, b: int) -> int:\n"
    "    return a b\n"
    "```\n"
)

invalid_result = validator.validate_response(invalid_response)

assert invalid_result.valid is False
assert invalid_result.error is not None
assert "syntax error" in invalid_result.error.lower()


plain_text_result = validator.validate_response(
    "This response contains no Python code."
)

assert plain_text_result.valid is True
assert plain_text_result.code is None

print("Python code validator passed")
