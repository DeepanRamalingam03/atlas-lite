from __future__ import annotations

from services.prompt_builder import PromptBuilder


builder = PromptBuilder()

initial = builder.build_initial_prompt(
    goal="Create calculator.",
    manager_instruction="Create calculator.py with add function.",
)

assert "Create calculator." in initial
assert "Create calculator.py with add function." in initial
assert "Return valid JSON only" in initial

retry = builder.build_retry_prompt(
    goal="Create calculator.",
    manager_instruction="Create calculator.py with add function.",
    manager_review="Missing validation.",
    test_output="SyntaxError line 10",
)

assert "Missing validation." in retry
assert "SyntaxError line 10" in retry
assert "ORIGINAL MANAGER INSTRUCTION" in retry
assert "Return valid JSON only." in retry

print("Prompt builder passed")
