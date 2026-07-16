# Atlas Continuous Orchestration — Handoff

## Final Objective

Atlas must run continuously on AWS and execute the approved project roadmap
without waiting for routine human approvals.

Normal development flow:

ChatGPT Architect Guidance
-> Atlas Continuous Orchestrator
-> OpenAI Manager and Reviewer
-> Gemini Worker
-> Project Knowledge and Relevant Files
-> Structured Change Proposal
-> Safe Staging
-> Syntax and Test Validation
-> Automatic Apply
-> Git Commit and Push to Approved Development Branch
-> Update Current State
-> Select Next Task
-> Repeat Continuously

## Human Role

Human intervention is required only for:

- secrets or missing credentials,
- login, OTP, MFA, or CAPTCHA,
- Constitution or major architecture changes,
- destructive or irreversible operations,
- production deployment,
- paid resources,
- live trading,
- broker credentials,
- trading risk limits,
- unrecoverable blockers.

Routine source-code and test changes must not require per-change approval.

## ChatGPT Architect Role

ChatGPT remains the external chief architect above Atlas.

Iteration flow:

Atlas status and architecture report
-> ChatGPT review and guidance
-> Architect directive imported into Atlas
-> Atlas continues autonomous execution

Future feature:

- ChatGPT conversation export importer
- Architect directive channel
- Architect report generator
- source traceability

## Existing Completed Foundation

- Discord bot
- OpenAI manager
- Gemini worker
- intent router
- persistent conversation memory
- Constitution loader
- project scanner
- project indexer
- project context builder
- project knowledge service
- relevant file selector
- safe file reader
- planner
- task decomposer
- dependency validator
- task scheduler
- plan state store
- execution coordinator
- task result store
- worker task executor
- plan runner
- safe staging workspace
- isolated validation runner
- diff generator
- approval gate
- transactional apply and rollback
- optional Git commit
- structured change proposal parser
- workflow models
- workflow state store

## Immediate Goal

Finish the bootstrap continuous orchestrator.

Required remaining runtime components:

1. autonomy policy
2. continuous orchestrator loop
3. roadmap task selector
4. recovery and retry manager
5. runtime process lock
6. Discord build controls
7. systemd service
8. end-to-end autonomous self-build test

## Operating Rules

- Stability is more important than speed.
- Use complete Bash copy-paste blocks.
- Do not ask for manual code edits.
- Run tests before commits and pushes.
- Do not expose or commit secrets.
- Do not modify Constitution automatically.
- Do not force-push.
- Do not enable live trading automatically.
- Do not create random work after the roadmap is complete.
- Pause only genuinely blocked tasks; continue independent work when possible.
