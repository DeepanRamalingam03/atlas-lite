from __future__ import annotations

import argparse

import config
from clients.factory import ClientFactory
from managers.openai_manager import OpenAIManager
from orchestrator.pipeline import AtlasPipeline
from services.prompt_builder import PromptBuilder
from services.review_parser import ReviewParser
from services.worker_output_parser import WorkerOutputParser
from testing.runner import StagingTestRunner
from utils.logger import setup_logger
from workers.gemini_worker import GeminiWorker
from workspace.writer import WorkspaceWriter


def build_pipeline() -> AtlasPipeline:
    staging_root = ".atlas_staging"

    return AtlasPipeline(
        manager=OpenAIManager(
            client=ClientFactory.create("openai"),
        ),
        worker=GeminiWorker(
            client=ClientFactory.create("gemini"),
        ),
        prompt_builder=PromptBuilder(),
        parser=WorkerOutputParser(),
        review_parser=ReviewParser(),
        workspace_writer=WorkspaceWriter(
            staging_root=staging_root,
        ),
        test_runner=StagingTestRunner(
            staging_root=staging_root,
            timeout_seconds=config.CLIENT_TIMEOUT,
        ),
        max_iterations=config.MAX_REVIEW_ITERATIONS,
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Atlas Lite autonomous staging pipeline."
    )

    parser.add_argument(
        "goal",
        help="High-level software development goal.",
    )

    return parser.parse_args()


def main() -> None:
    logger = setup_logger("atlas-lite.main")
    args = parse_arguments()

    logger.info("Starting Atlas Lite development pipeline.")

    result = build_pipeline().execute(args.goal)

    print("\n" + "=" * 72)
    print("ATLAS LITE PIPELINE RESULT")
    print("=" * 72)
    print(f"Approved   : {result.approved}")
    print(f"Iterations : {result.iterations}")
    print(f"Summary    : {result.summary or 'None'}")
    print(f"Test Pass  : {result.test_result.success}")

    print("\nITERATION HISTORY")
    print("-" * 72)

    for record in result.history:
        print(
            f"Iteration {record.iteration}: "
            f"approved={record.approved}, "
            f"test_success={record.test_success}"
        )

    print("\nSTAGED FILES")
    print("-" * 72)

    if result.written_paths:
        for path in result.written_paths:
            print(path)
    else:
        print("No files staged.")

    print("\nMANAGER REVIEW")
    print("-" * 72)
    print(result.manager_review or "No review returned.")

    print("\nTEST OUTPUT")
    print("-" * 72)
    print(
        result.test_result.combined_output
        or "No test output."
    )

    print("=" * 72)

    if not result.approved:
        raise SystemExit(
            "Atlas Lite stopped because the pipeline was not approved."
        )


if __name__ == "__main__":
    main()
