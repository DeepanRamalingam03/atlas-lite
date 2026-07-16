from __future__ import annotations

import shutil
from pathlib import Path

from core.memory_store import PersistentMemoryStore


test_root = Path(".atlas_memory_test")
storage_path = test_root / "memory.json"

if test_root.exists():
    shutil.rmtree(test_root)

memory = PersistentMemoryStore(
    storage_path=storage_path,
    max_turns_per_user=4,
)

memory.append_exchange(
    user_id=123,
    user_message="First question",
    assistant_message="First answer",
)

assert memory.history_size(123) == 2

memory.append_exchange(
    user_id=123,
    user_message="Second question",
    assistant_message="Second answer",
)

assert memory.history_size(123) == 4

memory.append_exchange(
    user_id=123,
    user_message="Third question",
    assistant_message="Third answer",
)

history = memory.get_history(123)

assert len(history) == 4
assert history[0].content == "Second question"
assert history[-1].content == "Third answer"

reloaded_memory = PersistentMemoryStore(
    storage_path=storage_path,
    max_turns_per_user=4,
)

assert reloaded_memory.history_size(123) == 4

reloaded_memory.clear(123)

assert reloaded_memory.history_size(123) == 0

shutil.rmtree(test_root)

print("Persistent memory store passed")
