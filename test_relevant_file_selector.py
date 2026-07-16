from __future__ import annotations

import shutil
from pathlib import Path

from services.project.relevant_file_selector import (
    RelevantFileSelector,
)


test_root = Path(
    ".atlas_relevant_file_selector_test"
)

if test_root.exists():
    shutil.rmtree(test_root)

(test_root / "discord_gateway").mkdir(
    parents=True
)
(test_root / "core").mkdir(parents=True)
(test_root / "trading").mkdir(parents=True)

(
    test_root
    / "discord_gateway"
    / "bot.py"
).write_text(
    "from core.assistant_manager import "
    "AtlasAssistantManager\n\n"
    "class AtlasDiscordBot:\n"
    "    async def ask_command(self) -> None:\n"
    "        return None\n\n"
    "    async def ping_command(self) -> None:\n"
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

(
    test_root
    / "trading"
    / "risk_engine.py"
).write_text(
    "class TradingRiskEngine:\n"
    "    def validate_order(self) -> bool:\n"
    "        return True\n",
    encoding="utf-8",
)

(
    test_root
    / "unrelated.py"
).write_text(
    "def calculate_weather() -> str:\n"
    "    return 'sunny'\n",
    encoding="utf-8",
)

selector = RelevantFileSelector(
    max_selected_files=5,
    minimum_score=2,
)

discord_files = selector.select(
    project_root=test_root,
    request=(
        "Modify the Discord ask command "
        "in AtlasDiscordBot"
    ),
)

discord_paths = [
    item.path
    for item in discord_files
]

assert (
    "discord_gateway/bot.py"
    in discord_paths
)

assert discord_paths[0] == (
    "discord_gateway/bot.py"
)

assert any(
    "exact symbol phrase" in reason
    or "symbol AtlasDiscordBot" in reason
    for reason in discord_files[0].reasons
)

manager_files = selector.select(
    project_root=test_root,
    request=(
        "Update AtlasAssistantManager ask method"
    ),
)

manager_paths = [
    item.path
    for item in manager_files
]

assert (
    "core/assistant_manager.py"
    in manager_paths
)

trading_files = selector.select(
    project_root=test_root,
    request=(
        "Improve trading risk order validation"
    ),
)

trading_paths = [
    item.path
    for item in trading_files
]

assert (
    "trading/risk_engine.py"
    in trading_paths
)

unmatched_files = selector.select(
    project_root=test_root,
    request=(
        "Build a photon observatory "
        "spectrometer controller"
    ),
)

assert unmatched_files == []

rendered = selector.render(
    discord_files
)

assert "discord_gateway/bot.py" in rendered
assert "score:" in rendered
assert "reasons:" in rendered

shutil.rmtree(test_root)

print("Relevant file selector passed")
