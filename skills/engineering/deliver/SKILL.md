---
name: deliver
description: Take the ADR and tickets from a grilling session to the integration branch and its dev deploy with sub-agents. Opus builds each ticket, Haiku flags it once, tickets collect on a batch branch, and one correctness and one quality review on Opus gate the batch. Sub-commands run (the default), status, setup.
disable-model-invocation: true
---

# Deliver

`/deliver <ADR path | ticket ids> [--into <branch>]` runs the tickets to the integration branch and the environment it deploys to, and stops only when it needs the user. Read the playbook for the command in full before doing anything else. With no arguments, print the table below and stop.

| Command | Playbook | Reads | Produces |
|---|---|---|---|
| `<ADR \| tickets>` | `reference/run.md` | the profile, the tickets, the ADR, `.deliver/state.json` | batches merged to the integration branch and deployed; tickets done; follow-up tickets; a cost row |
| `status` | `reference/status.md` | the state file | a table, no model work |
| `setup` | `reference/setup.md` | the repositories, their CLAUDE.md, an existing profile | `docs/agents/delivery-profile.md`, role agents in `.claude/agents/` |

## Words

- **Batch**: the tickets delivered together through one batch branch per repository and one final review.
- **Integration branch**: where batches land, from the profile or `--into`; it may be the development branch or a long-lived branch for one body of work.
- **Flag**: a ticket reviewer's unverified suspicion, answered by the implementer and ruled on by the final review.
- **Finding**: a defect the final review verified, with a severity (Blocking, Should-fix, Nit) or marked Follow-up when it lies outside the batch's own code.
- **Delivered**: merged to the integration branch and running wherever that branch deploys.

## Principles

- **The grilling is the plan.** The ADR and the tickets are the only build input. There is no plan or spec phase; `run` checks each ticket against a bar and fixes it in the tracker before building.
- **The implementer decides the technical calls.** It records each one under `Decisions:` in its commit, and the final review checks them against the ADR. Only product, scope and ADR questions reach the user.
- **Cheap review per ticket, strong review per batch.** A Haiku ticket reviewer flags each ticket once. A correctness reviewer and a quality reviewer on Opus read the whole batch, rule on every flag, and hand one fixer one round. A confirm pass runs only after a Blocking finding.
- **Context is the cost.** Cost scales with context size times calls, so every agent is fresh per ticket or per batch, has an explicit tools list with no MCP servers, and reports in under 300 words; the final reviewers' report is their findings, in under 900. The orchestrator reads reports and script output, never transcripts. The user's settings cap every session at 300k tokens (`autoCompactWindow`).
- **One or two tickets at a time.** Each ticket branches from the batch head, so nothing rebases and nothing needs locks or grants.
- **Everything project-specific lives in the profile.** The skill never names a tracker, a host, a branch or a test runner.
- **State lives in files.** `.deliver/state.json`, `tickets.md`, the flag files and the findings files let a cold session resume.
- **Measure.** `scripts/cost.py` writes one row per batch to `.deliver/costs.md`. The target is 12M weighted tokens per ticket or less (ADR 0001).

## Skills this one calls

`tdd`, `diagnosing-bugs`, `resolving-merge-conflicts` and `codebase-design` from inside the implementer and fixer templates. `grilling` runs before `/deliver`, in the same session when possible, so the orchestrator already holds the decisions.
