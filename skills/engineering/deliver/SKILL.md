---
name: deliver
description: Take the ADR and tickets from a grilling session to the integration branch and its dev deploy with sub-agents. Opus builds each ticket and answers its risk checks, tickets collect on a batch branch, and one correctness and one quality review on Opus gate the batch. Sub-commands run (the default), status, setup.
disable-model-invocation: true
---

# Deliver

`/deliver <ADR path | ticket ids> [--into <branch>] [--model <role>=<model>] [--effort <role>=<effort>]` runs the tickets to the integration branch and the environment it deploys to, and stops only when it needs the user. Read the playbook for the command in full before doing anything else. With no arguments, print the table below and stop.

| Command | Playbook | Reads | Produces |
|---|---|---|---|
| `<ADR \| tickets>` | `reference/run.md` | the profile, the tickets, the ADR, `.deliver/state.json` | batches merged to the integration branch and deployed; tickets done; added tickets for in-scope work too big to fix on the way; follow-up tickets for the rest; a cost row |
| `status` | `reference/status.md` | the state file | a table, no model work |
| `setup` | `reference/setup.md` | the repositories, their CLAUDE.md, an existing profile | `docs/agents/delivery-profile.md`, role agents in `.claude/agents/` |

## Words

- **Batch**: the tickets delivered together through one batch branch per repository and one final review.
- **Integration branch**: where batches land, from the profile or `--into`; it may be the development branch or a long-lived branch for one body of work.
- **Risk checks**: the implementer's answers, in its commit, to the questions its ticket's risk tags raise and to three it always answers (inputs, existing paths, reuse). The final review checks each one.
- **In scope**: work the ADR's outcome needs, or that sits in code the grilling's tickets change or call directly. Added tickets don't widen it.
- **In-passing fix**: an in-scope defect outside its ticket's own work that the implementer fixes on its ticket branch, test first, and lists under `In passing:` in its commit.
- **Added ticket**: a ticket the run files itself for in-scope work too big for an in-passing fix or the fix round, from the draft of the agent that found it. It goes through intake into a later batch of the run.
- **Follow-up**: a backlog ticket for work that is out of scope, or that only a person can do or decide. The run never builds it; one that needs a person is assigned to the user.
- **Carry list**: `.deliver/<slug>/carry.md`, what the batch has to act on that no diff shows: items a handoff or an earlier batch left, and what implementers found and didn't fix. Every item is resolved, made a finding, made an added ticket, filed as a follow-up or dropped before the fix round.
- **Finding**: an in-scope defect the final review verified, with a severity (Blocking, Should-fix, Nit). The fixer fixes it whether or not the batch wrote that code.
- **Run**: one `/deliver`, from intake until the last queued ticket is delivered or the weekly cap stops it. It may deliver several batches.
- **Delivered**: merged to the integration branch and running wherever that branch deploys.
- **Continuation**: a fresh agent of the same role that carries on an earlier one's work from its worktree or fix branch, with the earlier brief and either one thing to do or the rest of the work. It takes the place of resuming an agent, which a workflow doesn't allow.

## Principles

- **The grilling is the plan.** The ADR and the tickets are the only build input. There is no plan or spec phase; `run` checks each ticket against a bar and fixes it in the tracker before building.
- **The implementer decides the technical calls.** It records each one under `Decisions:` in its commit, and the final review checks them against the ADR. Only product, scope and ADR questions reach the user.
- **Self-check per ticket, strong review per batch.** Each implementer answers its ticket's risk checks from the code, including code outside its diff. A correctness reviewer and a quality reviewer on Opus read the whole batch, starting from those answers and the carry list, and hand one fixer one round. A confirm pass reads the fix round's delta only after a Blocking finding, or when the fixer changed more than about 150 production lines outside the batch's code or touched a risk area there. ADR 0002 records why the Haiku ticket reviewer went.
- **Fix what's in scope now.** An agent that finds an in-scope defect fixes it while it holds the context: an implementer in passing, up to about 200 production lines per ticket; the fixer for each finding of up to about 200 lines. Bigger in-scope work becomes an added ticket, drafted in full by the agent that found it, for a later batch of the same run. Only out-of-scope work and what needs a person become follow-ups (ADR 0004).
- **Context is the cost.** Cost scales with context size times calls, so every agent is fresh per ticket or per batch, has an explicit tools list with no MCP servers, and reports in under 300 words; the final reviewers' report is their findings, in under 900. The tracker clerk is the one agent with an MCP server: it holds the tracker's tools, so the issues they echo back never reach the orchestrator. The orchestrator reads reports and script output, never transcripts, and copies the final reviewers' findings with `scripts/save-report.py` instead of retyping them. Each deliver workspace's `.claude/settings.local.json` sets `autoCompactWindow` to 500000, so a final reviewer reads a full batch without compacting (ADR 0004).
- **The batch shows as it runs.** Every agent runs in a workflow named for its step (`deliver <slug> · ATE-543`, `deliver <slug> · final review`), so the user's background tasks show each ticket, review and fix as it happens, with each agent's model. The orchestrator stays in this session and launches each one; `scripts/workflow.py` renders the script and gives each agent its role's model and effort: the role agent's frontmatter by default, changed for the workspace in the profile's Agents table or for one run with `--model` and `--effort` (ADR 0003).
- **One or two tickets at a time.** Each ticket branches from the batch head, so nothing rebases and nothing needs locks or grants.
- **Everything project-specific lives in the profile.** The skill never names a tracker, a host, a branch or a test runner.
- **State lives in files.** `.deliver/state.json`, `tickets.md`, the carry list, the notes (the user's standing instructions for the run) and the findings files let a cold session resume.
- **One session owns a batch.** `state.py` refuses writes from any other session until it claims the batch, which it does only after asking the user.
- **Measure.** `scripts/cost.py` writes one row per batch to `.deliver/costs.md`. The target is 12M weighted tokens per ticket or less (ADR 0001).

## Skills this one calls

`tdd`, `diagnosing-bugs`, `resolving-merge-conflicts` and `codebase-design` from inside the implementer and fixer templates. `grilling` runs before `/deliver`, in the same session when possible, so the orchestrator already holds the decisions.
