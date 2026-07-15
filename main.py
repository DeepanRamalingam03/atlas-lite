from __future__ import annotations

import argparse

import config
from clients.factory import ClientFactory
from managers.openai_manager import OpenAIManager
from orchestrator.ai_cycle import AICycleOrchestrator
from utils.logger import setup_logger
from workers.gemini_worker import GeminiWorker


def build_orchestrator() -> AICycleOrchestrator:
    manager_client = ClientFactory.create("openai")
    worker_client = ClientFactory.create("gemini")

    manager = OpenAIManager(client=manager_client)
    worker = GeminiWorker(client=worker_client)

    return AICycleOrchestrator(
        manager=manager,
        worker=worker,
        max_iterations=config.MAX_REVIEW_ITERATIONS,
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one Atlas Lite Manager-Worker orchestration cycle."
    )
    parser.add_argument(
        "goal",
        help="High-level development goal for the manager.",
    )
    return parser.parse_args()


def main() -> None:
    logger = setup_logger("atlas-lite.main")
    args = parse_arguments()

    logger.info("Starting Atlas Lite AI orchestration cycle.")

    orchestrator = build_orchestrator()
    result = orchestrator.execute(args.goal)

    print("\n" + "=" * 72)
    print("ATLAS LITE RESULT")
    print("=" * 72)
    print(f"Approved   : {result.approved}")
    print(f"Iterations : {result.iterations}")
    print("\nMANAGER REVIEW")
    print("-" * 72)
    print(result.manager_review)
    print("\nWORKER OUTPUT")
    print("-" * 72)
    print(result.worker_output)
    print("=" * 72)

    if not result.approved:
        raise SystemExit(
            "Atlas Lite stopped because the maximum review iterations were reached."
        )


if __name__ == "__main__":
    main()
