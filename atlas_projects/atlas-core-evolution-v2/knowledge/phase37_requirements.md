# Phase 37 Knowledge — Deterministic Review Guard

## Purpose

Add deterministic evidence checks before AI manager approval and release.

The deterministic guard complements the OpenAI manager; it does not replace
repository grounding, tests, or manager review.

## Required guard categories

At minimum evaluate:

- unsafe or absolute paths
- parent-directory traversal
- files outside allowed repository scope
- unexpected files relative to the task
- unrelated broad changes
- duplicate implementation indicators
- existing helper or service reuse evidence
- required test presence when behavior changes
- empty or invalid staged output
- staged versus tracked repository distinction
- protected or constitution-sensitive paths
- dependency and import integrity when deterministically measurable
- acceptance-criteria evidence

## Decision model

Return structured evidence containing:

- passed
- failed
- warnings
- category
- reason
- affected paths
- deterministic evidence
- whether human approval is required

A deterministic failure must prevent release even if AI review says approved.

Warnings may reach the manager as review evidence but must not automatically
be treated as failures unless policy requires it.

## Safety rules

- Do not claim semantic correctness from static checks alone.
- Do not use vague keyword matching as final proof of architecture duplication.
- Do not silently delete worker output.
- Do not automatically modify constitution or protected files.
- Keep guard output bounded.
- Preserve existing review response compatibility.

## Integration expectation

Recommended order:

1. worker output parsed
2. staged files written
3. deterministic validation/tests
4. deterministic review guard
5. manager review using guard evidence
6. approve only when all required gates pass

## Required tests

Include:

- approved safe change
- unsafe path rejection
- unrelated file rejection where scope is explicit
- missing required tests
- deterministic failure overriding manager approval
- warnings reaching manager evidence
- protected path requiring human handling
- legacy pipeline behavior when guard is disabled
