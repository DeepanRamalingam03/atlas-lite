from __future__ import annotations

from services.prompt_builder import PromptBuilder


builder = PromptBuilder()

initial = builder.build_initial_prompt(
    goal="Create calculator.",
    manager_instruction="Create calculator.py with add function.",
)

assert "Create calculator." in initial
assert "Create calculator.py with add function." in initial

retry = builder.build_retry_prompt(
    goal="Create calculator.",
    manager_instruction="Create calculator.py with add function.",
    rejection_reason="Missing validation.",
    fix_instruction="Add input validation.",
    test_output="SyntaxError line 10",
    iteration=2,
)

assert "RETRY ITERATION 2" in retry
assert "Missing validation." in retry
assert "Add input validation." in retry
assert "SyntaxError line 10" in retry

print("Prompt builder passed")
