# Phase 38 Knowledge — Repository Relationship Index

## Purpose

Create a deterministic, commit-aware repository relationship index that helps
repository grounding choose more relevant files with less prompt context.

## Required relationships

Where deterministically available:

- Python file to imported local modules
- source file to likely test files
- test file to imported source modules
- package to child modules
- module to referenced classes and functions
- file to relevant documentation by verified references or naming
- file to related configuration
- file to recent related Git commits when safely obtainable

## Required metadata

The index must include:

- repository root
- current Git commit
- generation timestamp
- tracked-file count
- indexed-file count
- relationship count
- schema version
- bounded per-file relationships
- ignored or unsupported file counts

## Freshness rules

- The current Git commit is the freshness key.
- Do not use an index built for a different commit as verified evidence.
- Regenerate or reject stale indexes.
- Untracked files must not become repository facts.
- Generated staging files must remain separate from tracked repository facts.
- Index writes must be atomic.
- Corrupt indexes must fail safely and be rebuildable.

## Scope rules

Initial implementation should favor deterministic Python repository analysis.
Do not attempt a universal language server or external vector database.

Use Python AST or equivalent deterministic parsing where appropriate.
Syntax failures in one file must not corrupt the entire index; record them as
bounded indexing failures.

## Grounding integration

Repository grounding may use the index to:

- expand directly relevant files
- include local imports
- include related tests
- include closely related configuration or documentation
- reduce irrelevant repository content

The index must remain advisory. Actual Git-tracked file contents remain the
source of truth.

## Required tests

Include:

- local import relationship
- source-to-test relationship
- test-to-source relationship
- stale commit rejection
- untracked file exclusion
- corrupt index recovery
- atomic persistence
- bounded relationships
- grounding integration
- backward compatibility when index is disabled or missing
