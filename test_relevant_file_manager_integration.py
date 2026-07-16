from __future__ import annotations

import shutil
from pathlib import Path

from clients.base_client import BaseClient
from core.assistant_manager import AtlasAssistantManager
from core.intent_router import IntentRouter
from core.memory_store import PersistentMemoryStore
from services.code_validator import PythonCodeValidator
from services.constitution_loader import ConstitutionLoader
from services.project.project_context_builder import (
    ProjectContextBuilder,
)
from services.project.project_knowledge_service import (
    ProjectKnowledgeService,
)
from services.project.project_memory import ProjectMemory
from services.project.project_scanner import ProjectScanner
from services.project.relevant_file_context_service import (
    RelevantFileContextService,
)
from services.project.relevant_file_selector import (
    RelevantFileSelector,
)


class FakeGeminiClient(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        return (
            "```python\n"
            "def updated_ask_command() -> str:\n"
            "    return 'updated'\n"
            "```"
        )


class FakeOpenAIClient(BaseClient):
    def __init__(self) -> None:
        self.prompts: list[str] = []

    def generate(self, prompt: str) -> str:
        self.prompts.append(prompt)

        if "WORKER RESPONSE" in prompt:
            return (
                "DECISION: APPROVED\n\n"
                "REASON:\n"
                "The implementation is valid and was reviewed "
                "against the selected project file contents.\n\n"
                "FIX_INSTRUCTION:\n"
                "NONE"
            )

        return (
            "Manager response using actual relevant "
            "project file contents."
        )


test_root = Path(".atlas_relevant_manager_test")
project_root = test_root / "sample_project"

if test_root.exists():
    shutil.rmtree(test_root)

(project_root / "discord_gateway").mkdir(
    parents=True,
)
(project_root / "core").mkdir(
    parents=True,
)

(
    project_root
    / "discord_gateway"
    / "bot.py"
).write_text(
    "from core.assistant_manager import "
    "AtlasAssistantManager\n\n"
    "class AtlasDiscordBot:\n"
    "    async def ask_command(self) -> None:\n"
    "        return None\n",
    encoding="utf-8",
)

(
    project_root
    / "core"
    / "assistant_manager.py"
).write_text(
    "class AtlasAssistantManager:\n"
    "    def ask(self, request: str) -> str:\n"
    "        return request\n",
    encoding="utf-8",
)

(project_root / ".env").write_text(
    "SECRET_MUST_NOT_LEAK=value\n",
    encoding="utf-8",
)

constitution_loader = ConstitutionLoader()
scanner = ProjectScanner()

context_builder = ProjectContextBuilder(
    constitution_loader=constitution_loader,
    scanner=scanner,
)

knowledge_service = ProjectKnowledgeService(
    context_builder=context_builder,
    memory=ProjectMemory(
        storage_path=(
            test_root / "project_memory.json"
        ),
    ),
)

relevant_context_service = RelevantFileContextService(
    project_root=project_root,
    selector=RelevantFileSelector(
        max_selected_files=5,
        minimum_score=2,
    ),
    max_files=5,
    max_total_characters=50_000,
)

openai = FakeOpenAIClient()
gemini = FakeGeminiClient()

manager = AtlasAssistantManager(
    clients={
        "openai": openai,
        "gemini": gemini,
    },
    router=IntentRouter(),
    memory=PersistentMemoryStore(
        storage_path=(
            test_root / "conversation_memory.json"
        ),
        max_turns_per_user=6,
    ),
    code_validator=PythonCodeValidator(),
    constitution_loader=constitution_loader,
    project_scanner=scanner,
    project_context_builder=context_builder,
    project_knowledge_service=knowledge_service,
    relevant_file_context_service=(
        relevant_context_service
    ),
    project_root=project_root,
    max_code_retries=2,
)

coding_result = manager.ask(
    user_id=900,
    request=(
        "Create Python code to modify the "
        "AtlasDiscordBot ask_command method"
    ),
)

assert coding_result.route.provider == "gemini"
assert coding_result.iterations == 1
assert "updated_ask_command" in coding_result.answer
assert len(gemini.prompts) == 1

assert (
    "discord_gateway/bot.py"
    in manager.relevant_file_paths
)

assert (
    "class AtlasDiscordBot"
    in manager.relevant_file_context
)

worker_prompt = gemini.prompts[-1]

assert (
    "REQUEST-SPECIFIC PROJECT FILES"
    in worker_prompt
)
assert (
    "FILE: discord_gateway/bot.py"
    in worker_prompt
)
assert "class AtlasDiscordBot" in worker_prompt
assert "async def ask_command" in worker_prompt
assert "SECRET_MUST_NOT_LEAK" not in worker_prompt

review_prompt = openai.prompts[-1]

assert "WORKER RESPONSE" in review_prompt
assert (
    "REQUEST-SPECIFIC PROJECT FILES"
    in review_prompt
)
assert "class AtlasDiscordBot" in review_prompt
assert "SECRET_MUST_NOT_LEAK" not in review_prompt
assert "DECISION: APPROVED" in (
    coding_result.manager_review
)

planning_result = manager.ask(
    user_id=900,
    request=(
        "Plan architecture changes for the "
        "AtlasAssistantManager ask method"
    ),
)

assert planning_result.route.provider == "openai"

assert (
    "core/assistant_manager.py"
    in manager.relevant_file_paths
)

planning_prompt = openai.prompts[-1]

assert (
    "FILE: core/assistant_manager.py"
    in planning_prompt
)
assert (
    "class AtlasAssistantManager"
    in planning_prompt
)
assert "SECRET_MUST_NOT_LEAK" not in planning_prompt

shutil.rmtree(test_root)

print(
    "Relevant file manager integration passed"
)
