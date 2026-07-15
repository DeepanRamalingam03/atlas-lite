from __future__ import annotations

import json
from pathlib import Path

from managers.base_manager import BaseManager
from orchestrator.pipeline import AtlasPipeline
from services.prompt_builder import PromptBuilder
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestRunner
from workers.base_worker import BaseWorker
from workspace.writer import WorkspaceWriter


class FakeManager(BaseManager):
    def create_worker_prompt(self, goal: str) -> str:
        return f"Implement this goal exactly: {goal}"

    def review_worker_output(
        self,
        goal: str,
        worker_prompt: str,
        worker_output: str,
    ) -> str:
        if "Success: True" in worker_output:
            return (
                "DECISION: APPROVED\n\n"
                "REASON:\n"
                "Implementation compiled successfully.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return (
            "DECISION: REJECTED\n\n"
            "REASON:\n"
            "Compilation failed.\n\n"
            "FIX_INSTRUCTION:\n"
            "Correct the syntax error."
        )


class FakeWorker(BaseWorker):
    def execute(self, instruction: str) -> str:
        payload = {
            "summary": "Created add_numbers function.",
            "files": [
                {
                    "path": "math_utils.py",
                    "content": (
                        "def add_numbers(a: int, b: int) -> int:\n"
                        "    return a + b\n"
                    ),
                }
            ],
        }

        return json.dumps(payload)


staging_root = Path(".atlas_pipeline_test")
writer = WorkspaceWriter(staging_root=staging_root)
writer.clear()

pipeline = AtlasPipeline(
    manager=FakeManager(),
    worker=FakeWorker(),
    prompt_builder=PromptBuilder(),
    parser=WorkerOutputParser(),
    workspace_writer=writer,
    test_runner=StagingTestRunner(
        staging_root=staging_root,
        timeout_seconds=30,
    ),
    max_iterations=2,
)

result = pipeline.execute(
    "Create a function that adds two integers."
)

assert result.approved is True
assert result.iterations == 1
assert result.test_result.success is True
assert len(result.file_changes) == 1
assert (staging_root / "math_utils.py").exists()

writer.clear()
staging_root.rmdir()

print("Atlas pipeline passed")
