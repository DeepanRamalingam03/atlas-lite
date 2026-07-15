from __future__ import annotations

import json
from pathlib import Path

from managers.base_manager import BaseManager
from orchestrator.pipeline import AtlasPipeline
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewParser
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestRunner
from workers.base_worker import BaseWorker
from workspace.writer import WorkspaceWriter


class FakeManager(BaseManager):
    def __init__(self) -> None:
        self.review_count = 0

    def create_worker_prompt(self, goal: str) -> str:
        return f"Implement this goal exactly: {goal}"

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        self.review_count += 1

        if self.review_count == 1:
            return (
                "DECISION: REJECTED\n\n"
                "REASON:\n"
                "The implementation is missing type annotations.\n\n"
                "FIX_INSTRUCTION:\n"
                "Add type annotations to every function parameter "
                "and return value."
            )

        return (
            "DECISION: APPROVED\n\n"
            "REASON:\n"
            "Implementation compiled successfully and is complete.\n\n"
            "FIX_INSTRUCTION:\n"
            "NONE"
        )


class FakeWorker(BaseWorker):
    def __init__(self) -> None:
        self.execution_count = 0

    def execute(self, instruction: str) -> str:
        self.execution_count += 1

        if self.execution_count == 1:
            content = (
                "def add_numbers(a, b):\n"
                "    return a + b\n"
            )
        else:
            assert "Add type annotations" in instruction

            content = (
                "def add_numbers(a: int, b: int) -> int:\n"
                "    return a + b\n"
            )

        return json.dumps(
            {
                "summary": "Created add_numbers function.",
                "files": [
                    {
                        "path": "math_utils.py",
                        "content": content,
                    }
                ],
            }
        )


staging_root = Path(".atlas_pipeline_test")
writer = WorkspaceWriter(staging_root=staging_root)
writer.clear()

pipeline = AtlasPipeline(
    manager=FakeManager(),
    worker=FakeWorker(),
    prompt_builder=PromptBuilder(),
    parser=WorkerOutputParser(),
    review_parser=ReviewParser(),
    workspace_writer=writer,
    test_runner=StagingTestRunner(
        staging_root=staging_root,
        timeout_seconds=30,
    ),
    max_iterations=3,
)

result = pipeline.execute(
    "Create a typed function that adds two integers."
)

assert result.approved is True
assert result.iterations == 2
assert len(result.history) == 2
assert result.history[0].approved is False
assert result.history[1].approved is True
assert result.test_result.success is True

generated_content = (
    staging_root / "math_utils.py"
).read_text(encoding="utf-8")

assert "a: int" in generated_content
assert "-> int" in generated_content

writer.clear()
staging_root.rmdir()

print("Atlas intelligent retry pipeline passed")
