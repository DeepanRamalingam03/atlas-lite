# Atlas Core Evolution — Phase 36 to Phase 38

## Objective

This project validates Atlas as a dependency-aware autonomous engineering
project executor.

Atlas must complete three phases sequentially:

1. Phase 36 — Runtime Metrics and Engineering Analytics
2. Phase 37 — Deterministic Review Guard
3. Phase 38 — Repository Relationship Index

Atlas must not implement all phases as one combined change.

Each phase must be independently:

- repository grounded
- planned
- implemented
- tested
- reviewed
- committed
- pushed
- production verified

The next phase may begin only after the previous roadmap task reaches the
completed state.

## Existing capabilities that must remain working

- Continuous AWS runtime
- Roadmap dependency selection
- Process locking
- Workflow recovery and retry policy
- Repository grounding
- Intelligent execution planning
- Workflow execution memory
- OpenAI manager review
- Gemini worker execution
- Isolated staging
- Deterministic tests
- Safe apply and release
- Git commit and push
- Discord runtime controls
- Runtime heartbeat and alerts
- Token usage metering
- USD and INR cost estimation
- Project-folder runner

## Global constraints

- Preserve backward compatibility.
- Do not rewrite existing working systems without evidence.
- Do not create duplicate services or models.
- Use Git-tracked repository evidence as the source of truth.
- Do not modify `.env`, credentials, tokens, systemd secrets, or Git keys.
- Do not enable experimental parallel execution.
- Do not remove existing Discord commands.
- Do not weaken approval, validation, or release safety.
- Keep all persistent runtime state outside Git unless it is configuration,
  schema, or an intentionally tracked example.
- Every phase must include targeted tests and regression tests.
- A phase is not complete merely because code was generated.

## Completion standard

A phase is complete only when:

1. Required implementation exists.
2. Acceptance criteria are proven by tests.
3. Existing tests continue to pass.
4. Manager review approves the integrated change.
5. Git commit and push succeed.
6. Runtime, Discord, and alert services remain healthy.
7. Runtime heartbeat is current.
8. The roadmap task is marked completed.
