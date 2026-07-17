# Phase 36 Knowledge — Runtime Metrics and Engineering Analytics

## Purpose

Provide reliable engineering-performance visibility for Atlas autonomous
workflow execution.

## Required measurements

At minimum:

- total workflows
- completed workflows
- failed workflows
- blocked workflows
- approval rate
- retry rate
- average iterations per workflow
- maximum iterations
- average workflow duration
- average validation duration when available
- successful and failed provider requests
- input, output, cached, reasoning, and total tokens
- estimated USD and INR cost
- average INR per workflow
- common normalized failure reasons

## Data quality rules

- Derive metrics only from persisted verified Atlas state and existing usage
  records.
- Never fabricate historic records.
- Clearly distinguish missing data from zero.
- Historic data unavailable before metering must remain unavailable.
- Normalize failure reasons without storing raw prompts or secrets.
- Bound retained metrics records and report output.
- Use UTC timestamps for storage.
- Show report-generation time.
- Avoid double counting restarted or resumed workflows.

## Required Discord capability

Add a backward-compatible command such as:

`!metrics [today|week|all]`

The exact command may be adjusted only if repository evidence shows a better
existing command pattern.

The report should combine engineering workflow metrics with token and cost
summaries without duplicating the pricing engine.

## Architecture guidance

Prefer:

- one metrics model
- one bounded metrics store or verified aggregator
- one report builder
- one Discord-facing adapter
- explicit production wiring
- unit and integration tests

Reuse existing:

- workflow state store
- roadmap task store
- token usage ledger
- pricing engine
- Discord message chunking
- runtime heartbeat and alert stores

## Forbidden behavior

- Do not introduce an external database.
- Do not scrape system logs as the primary source when structured state exists.
- Do not store raw prompts.
- Do not perform live model requests to build reports.
- Do not change provider pricing logic unnecessarily.
