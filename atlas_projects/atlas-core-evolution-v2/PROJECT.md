# Atlas Core Evolution V2

Project ID: `atlas-core-evolution-v2`
Version: `2.0`

This project implements Atlas phases 36, 37, and 38 through
30 strict dependency-ordered mini tasks.

## Execution order

- Phase 36: `p36-01` through `p36-10`
- Phase 37: `p37-01` through `p37-10`
- Phase 38: `p38-01` through `p38-10`

Every task must:

- modify no more than its declared file limit;
- touch only explicitly allowed files;
- preserve existing repository code;
- avoid complete rewrites of existing files;
- run targeted validation;
- receive manager approval;
- commit and push one isolated change;
- finish before the next task begins.
