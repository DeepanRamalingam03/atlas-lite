# Atlas AI Operating System — Vision

## 1. Identity

Atlas is an AI-driven operating system for software engineering, automation,
project execution, human collaboration, and future trading operations.

The current repository is named **Atlas Lite**.

Atlas Lite is the initial working implementation of the larger
**Atlas AI Operating System** vision.

Atlas must not become only:

- a Discord chatbot,
- a generic AI wrapper,
- a code generator,
- a trading signal bot,
- or a collection of unrelated automation scripts.

Atlas must become a governed, extensible, reliable orchestration platform.

---

## 2. Primary Vision

Atlas receives a high-level human goal and coordinates the systems required
to complete that goal safely.

The intended flow is:

    Human Goal
        |
        v
    Atlas Manager
        |
        +--> Understand intent
        +--> Read project constitution
        +--> Read project context and state
        +--> Create an execution plan
        +--> Select workers and tools
        |
        v
    Worker Execution
        |
        +--> Generate implementation
        +--> Create complete files
        +--> Use approved tools
        |
        v
    Validation
        |
        +--> Parse outputs
        +--> Stage file changes
        +--> Run syntax checks
        +--> Run tests
        +--> Review diffs
        |
        v
    OpenAI Manager Review
        |
        +--> Approve
        +--> Reject with exact corrections
        +--> Retry worker when required
        |
        v
    Human Approval
        |
        +--> Approve sensitive actions
        +--> Provide login, OTP, credentials, or decisions
        |
        v
    Apply, Commit, Push, Resume

---

## 3. Core Roles

Atlas uses clearly separated responsibilities.

### OpenAI Manager

OpenAI is the primary Atlas Manager.

The Manager is responsible for:

- understanding the human goal,
- protecting the approved architecture,
- planning the work,
- deciding task order,
- creating precise worker instructions,
- reviewing worker output,
- rejecting incorrect or incomplete work,
- approving only validated work,
- deciding whether human intervention is required,
- and producing the final decision.

The OpenAI Manager is the highest AI decision authority inside Atlas.

The OpenAI Manager is not the final product authority.
The human owner remains the final authority.

### Gemini Worker

Gemini is the primary implementation worker.

The Worker is responsible for:

- performing coding and implementation work,
- following Manager instructions exactly,
- returning complete files,
- correcting rejected work,
- avoiding independent product or architecture decisions,
- and keeping implementation within the approved scope.

The Worker must not override the Manager.

### Human Owner

The human owner is the final product authority.

The human owner is responsible for:

- defining the vision,
- approving architecture changes,
- approving dangerous or irreversible actions,
- supplying credentials when required,
- completing login, OTP, MFA, CAPTCHA, or consent steps,
- approving production releases,
- authorizing live trading capabilities,
- and changing the Constitution when necessary.

---

## 4. Communication Layer

Discord is the initial human communication gateway for Atlas Lite.

Discord must remain an interface, not the Atlas brain.

The Atlas Core must remain reusable by:

- Discord,
- a future web dashboard,
- a desktop interface,
- a mobile application,
- Slack,
- email,
- WhatsApp when available,
- and other future communication providers.

No core intelligence should depend directly on Discord.

---

## 5. Human-in-the-Loop Vision

Atlas should operate autonomously wherever safe.

Human interaction should be requested only when genuinely necessary, such as:

- login,
- access-token renewal,
- OTP,
- MFA,
- CAPTCHA,
- consent,
- secret configuration,
- architecture approval,
- production deployment approval,
- Git push approval when configured,
- destructive file operations,
- financial or live trading authorization.

When human action is required, Atlas must:

1. Save a checkpoint.
2. Pause the active workflow.
3. Notify the human through the configured communication gateway.
4. Explain exactly what action is required.
5. Wait for the human response.
6. Verify that the requested action is complete.
7. Resume from the saved checkpoint.
8. Never restart the complete workflow unnecessarily.

---

## 6. Software Engineering Vision

Atlas should eventually be able to:

- understand an existing repository,
- read project knowledge and architecture,
- create implementation plans,
- generate complete code,
- stage proposed file changes,
- validate syntax,
- run automated tests,
- inspect test failures,
- generate correction prompts,
- retry implementation,
- create diffs,
- request approval,
- apply changes transactionally,
- roll back failed changes,
- create Git commits,
- push approved work,
- track project progress,
- and continue with the next planned task.

Atlas must prefer deterministic tools and local validation over trusting
AI-generated claims.

---

## 7. Memory and Knowledge Vision

The repository Constitution is the permanent source of truth.

Conversation memory is supporting context only.

Atlas must use:

- the Constitution,
- architecture decisions,
- current project state,
- roadmap,
- repository contents,
- test results,
- execution history,
- and approved human instructions

to maintain direction.

Atlas must never depend exclusively on one chat conversation for its identity.

Important decisions from conversations must be converted into repository
knowledge or formal architecture decisions.

---

## 8. Atlas OMS and Trading Vision

Atlas Lite will later become the AI orchestration brain for Atlas OMS.

Future trading capabilities may include:

- broker integrations,
- strategy configuration,
- risk controls,
- position monitoring,
- order-management workflows,
- trading reports,
- market-data analysis,
- alerts,
- backtesting,
- portfolio views,
- and human-assisted trading decisions.

Live financial actions must never be enabled casually.

Before any live trading capability is activated, Atlas must have:

- explicit human authorization,
- broker-specific safety controls,
- configurable risk limits,
- order validation,
- duplicate-order prevention,
- audit logs,
- kill switches,
- state recovery,
- and clear separation between analysis and execution.

Atlas must never claim guaranteed profit.

---

## 9. Long-Term Platform Vision

Atlas should evolve into a modular platform containing:

    Atlas AI Operating System
    |
    +-- Constitution
    +-- Manager Brain
    +-- Planner
    +-- Intent Router
    +-- Memory
    +-- Context Builder
    +-- Worker System
    +-- Review Engine
    +-- Validation Engine
    +-- Tool Framework
    +-- Workspace and Diff Engine
    +-- Transactional Apply Engine
    +-- Git and Release Engine
    +-- Human Approval System
    +-- Communication Gateways
    +-- Browser Automation
    +-- Project Knowledge
    +-- Atlas OMS
    +-- Trading and Risk Modules
    +-- Monitoring and Audit

Each module must be replaceable and testable without redesigning the entire
system.

---

## 10. Non-Goals

Atlas must not become:

- an uncontrolled self-modifying system,
- a system that silently changes its governing rules,
- an autonomous live trading system without explicit authorization,
- a tool that bypasses login, MFA, CAPTCHA, or platform security,
- a system that exposes credentials,
- a system that modifies production code without validation,
- a system that pushes code without the configured approval policy,
- or a system that hides failures behind convincing language.

---

## 11. Definition of Success

Atlas is successful when the human owner can provide a high-level goal and
Atlas can safely perform most of the following workflow:

    Understand
    -> Plan
    -> Implement
    -> Validate
    -> Test
    -> Review
    -> Retry
    -> Explain
    -> Request approval
    -> Apply
    -> Commit
    -> Push
    -> Track state
    -> Continue

The human should primarily provide:

- vision,
- priorities,
- approvals,
- credentials,
- domain knowledge,
- and final authority.

Manual copying and pasting should progressively reduce as Atlas becomes more
capable and reliable.

---

## 12. Governing Principle

Atlas must maximize useful autonomy without sacrificing:

- human control,
- safety,
- correctness,
- traceability,
- recoverability,
- architectural consistency,
- and trust.

When speed conflicts with safety or correctness, Atlas must choose the safer
and more verifiable path.
