from __future__ import annotations

import shutil
from pathlib import Path

from services.project.project_file_reader import (
    ProjectFileReader,
)
from services.project.relevant_file_context_service import (
    RelevantFileContextService,
)
from services.project.relevant_file_selector import (
    RelevantFileSelector,
)


test_root = Path(
    ".atlas_relevant_file_context_test"
)

if test_root.exists():
    shutil.rmtree(test_root)

(test_root / "discord_gateway").mkdir(
    parents=True
)
(test_root / "core").mkdir(parents=True)

(
    test_root
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
    test_root
    / "core"
    / "assistant_manager.py"
).write_text(
    "class AtlasAssistantManager:\n"
    "    def ask(self, request: str) -> str:\n"
    "        return request\n",
    encoding="utf-8",
)

(test_root / ".env").write_text(
    "SECRET=blocked\n",
    encoding="utf-8",
)

selector = RelevantFileSelector(
    max_selected_files=5,
    minimum_score=2,
)

reader = ProjectFileReader(
    project_root=test_root,
    max_file_bytes=10_000,
)

service = RelevantFileContextService(
    project_root=test_root,
    selector=selector,
    reader=reader,
    max_files=5,
    max_total_characters=50_000,
)

result = service.build(
    "Modify AtlasDiscordBot ask command"
)

selected_paths = [
    item.path
    for item in result.selected_files
]

content_paths = [
    item.path
    for item in result.file_contents
]

assert "discord_gateway/bot.py" in selected_paths
assert "discord_gateway/bot.py" in content_paths

assert "RELEVANT PROJECT FILE CONTEXT" in (
    result.rendered_context
)
assert "FILE: discord_gateway/bot.py" in (
    result.rendered_context
)
assert "class AtlasDiscordBot" in (
    result.rendered_context
)
assert "async def ask_command" in (
    result.rendered_context
)
assert "SCORE:" in result.rendered_context
assert "REASONS:" in result.rendered_context
assert "SECRET=blocked" not in (
    result.rendered_context
)

unmatched_result = service.build(
    "Build a photon observatory spectrometer controller"
)

assert unmatched_result.selected_files == ()
assert unmatched_result.file_contents == ()
assert unmatched_result.rendered_context == (
    "No relevant project files were selected "
    "for this request."
)

shutil.rmtree(test_root)

print("Relevant file context service passed")
