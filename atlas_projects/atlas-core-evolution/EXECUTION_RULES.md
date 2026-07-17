# Atlas Core Evolution Execution Rules

## Dependency rules

- `p36` has no project dependency and must execute first.
- `p37` depends on successful completion of `p36`.
- `p38` depends on successful completion of `p37`.
- A failed, blocked, paused, or running dependency does not satisfy a
  dependency.
- Do not manually bypass dependency checks.

## Repository rules

- Inspect existing implementations before adding new files.
- Reuse existing stores, models, controls, reports, and service builders.
- Do not infer file names that are not verified in the repository.
- New files must have a clear owner and purpose.
- Untracked files are not repository facts until deliberately staged.
- Avoid broad refactoring unrelated to the active phase.

## Implementation rules

- One phase equals one cohesive repository change.
- Keep public interfaces backward compatible unless the task explicitly
  requires a migration.
- Generic constructors must retain safe defaults.
- Production wiring must be explicit.
- Environment configuration must be read and validated eagerly.
- Configuration errors must fail safely before runtime work starts.
- Long prompts and stored records must be bounded.
- Never persist raw prompts, secrets, credentials, or complete model output
  as operational memory.

## Test rules

Each phase must include:

- compile validation
- unit tests for new behavior
- backward-compatibility tests
- failure-path tests
- production-construction tests
- integration tests with existing planning, grounding, memory, runtime, and
  Discord systems where applicable
- full non-live regression before release

Live OpenAI or Gemini API calls must not be used merely to prove wiring.

## Release rules

Before commit:

- run `git diff --check`
- stage only intended files
- run cached diff validation
- ensure no generated runtime state is staged

After commit:

- pull/rebase safely
- rerun important tests
- push to `origin/main`
- restart services safely
- verify Discord gateway connection
- verify runtime heartbeat
- verify Git working tree is clean and synchronized

## Failure rules

When a phase fails:

- identify the exact failing boundary
- retain useful verified progress
- use workflow execution memory
- do not repeat the same rejected implementation unchanged
- do not start the dependent phase
- stop after the configured retry budget and expose the blocker honestly
