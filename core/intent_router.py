from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Intent(str, Enum):
    GENERAL = "general"
    PLANNING = "planning"
    CODING = "coding"
    REVIEW = "review"
    TESTING = "testing"
    GIT = "git"
    TRADING = "trading"


@dataclass(slots=True, frozen=True)
class RouteDecision:
    intent: Intent
    provider: str
    reason: str


class IntentRouter:
    """
    Routes user requests to the most suitable Atlas provider.

    Current policy:
    - OpenAI: planning, architecture, review, decisions, general questions.
    - Gemini: coding, implementation, debugging, and test generation.
    """

    CODING_KEYWORDS = {
        "code",
        "coding",
        "implement",
        "implementation",
        "function",
        "class",
        "python",
        "javascript",
        "typescript",
        "api",
        "bug",
        "debug",
        "fix error",
        "exception",
        "traceback",
        "refactor",
    }

    TESTING_KEYWORDS = {
        "test case",
        "test cases",
        "unit test",
        "integration test",
        "pytest",
        "selenium",
        "playwright",
        "webdriverio",
        "appium",
        "automation test",
    }

    REVIEW_KEYWORDS = {
        "review",
        "audit",
        "check code",
        "code quality",
        "security review",
        "architecture review",
    }

    PLANNING_KEYWORDS = {
        "plan",
        "architecture",
        "design",
        "roadmap",
        "strategy",
        "organize",
        "prioritize",
        "decision",
        "approach",
    }

    GIT_KEYWORDS = {
        "git",
        "commit",
        "push",
        "branch",
        "merge",
        "pull request",
        "repository",
        "github",
    }

    TRADING_KEYWORDS = {
        "nifty",
        "banknifty",
        "option",
        "options",
        "ce",
        "pe",
        "strike",
        "trade",
        "trading",
        "portfolio",
        "position",
        "profit",
        "loss",
        "stop loss",
        "target",
        "kotak",
        "groww",
    }

    def route(self, request: str) -> RouteDecision:
        cleaned_request = request.strip().lower()

        if not cleaned_request:
            raise ValueError("Request cannot be empty.")

        if self._contains_any(cleaned_request, self.TRADING_KEYWORDS):
            return RouteDecision(
                intent=Intent.TRADING,
                provider="openai",
                reason="Trading request requires manager reasoning.",
            )

        if self._contains_any(cleaned_request, self.REVIEW_KEYWORDS):
            return RouteDecision(
                intent=Intent.REVIEW,
                provider="openai",
                reason="Review requests are handled by the manager model.",
            )

        if self._contains_any(cleaned_request, self.TESTING_KEYWORDS):
            return RouteDecision(
                intent=Intent.TESTING,
                provider="gemini",
                reason="Testing implementation is routed to the coding worker.",
            )

        if self._contains_any(cleaned_request, self.GIT_KEYWORDS):
            return RouteDecision(
                intent=Intent.GIT,
                provider="openai",
                reason="Git requests require safe planning and explanation.",
            )

        if self._contains_any(cleaned_request, self.CODING_KEYWORDS):
            return RouteDecision(
                intent=Intent.CODING,
                provider="gemini",
                reason="Coding request is routed to the Gemini worker.",
            )

        if self._contains_any(cleaned_request, self.PLANNING_KEYWORDS):
            return RouteDecision(
                intent=Intent.PLANNING,
                provider="openai",
                reason="Planning request is routed to the manager model.",
            )

        return RouteDecision(
            intent=Intent.GENERAL,
            provider="openai",
            reason="General requests are handled by the manager model.",
        )

    @staticmethod
    def _contains_any(
        text: str,
        keywords: set[str],
    ) -> bool:
        return any(keyword in text for keyword in keywords)
