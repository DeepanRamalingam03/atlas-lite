from __future__ import annotations

import os

from dotenv import load_dotenv


load_dotenv()

CLIENT_TIMEOUT = int(
    os.getenv("CLIENT_TIMEOUT", "120")
)

MAX_REVIEW_ITERATIONS = int(
    os.getenv("MAX_REVIEW_ITERATIONS", "3")
)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv(
    "OPENAI_MODEL",
    "gpt-5.1",
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash",
)

DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")
DISCORD_ALLOWED_USER_ID = os.getenv(
    "DISCORD_ALLOWED_USER_ID"
)
