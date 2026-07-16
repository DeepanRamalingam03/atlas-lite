from __future__ import annotations

from core.intent_router import Intent, IntentRouter


router = IntentRouter()

coding = router.route(
    "Create Python code for a calculator API."
)

assert coding.intent is Intent.CODING
assert coding.provider == "gemini"

planning = router.route(
    "Design the architecture and roadmap."
)

assert planning.intent is Intent.PLANNING
assert planning.provider == "openai"

testing = router.route(
    "Create WebDriverIO automation test cases."
)

assert testing.intent is Intent.TESTING
assert testing.provider == "gemini"

trading = router.route(
    "Explain the risk in my Nifty CE and PE strategy."
)

assert trading.intent is Intent.TRADING
assert trading.provider == "openai"

print("Intent router passed")
