---
status: accepted
---

# Deliver builds from tickets, reviews cheaply per ticket and strongly per batch

`deliver` no longer plans or specs. The ADR and Linear tickets a grilling session writes are the build input. An Opus implementer builds each ticket and records its own technical decisions. A Haiku ticket reviewer flags each ticket once. Tickets collect on a batch branch, and one final review (a correctness reviewer and a quality reviewer, both Opus, one fix round) runs before the batch goes to the integration branch and deploys. We chose this because the ATE-488 batch (2026-09-24/25) cost about 33M weighted tokens per merged PR and ran into the user's 5-hour and weekly limits. Two-thirds of that went to spec planners that wrote and proved each change in full (byte-exact files, hash pins, mutation probes, replays) before an implementer typed it again.

## Considered options

- **Lighter specs** (decisions and an acceptance list, no code). Rejected: the grilling session already holds the decisions, and a separate planner re-derives them at 500k tokens of context per call.
- **Cheaper reviewers on the old flow.** Rejected as the main lever: PR reviews on Opus were 0.4–0.6M each, about 5% of a PR. The cost was context size times calls. Planners averaged 534k tokens per call, and the orchestrator 509k over 526 calls.
- **A Workflow script as the orchestrator.** Rejected: a script cannot ask the user a question, wait for a limit to reset, or read and write files, and it resumes only in the session that started it.
- **Sonnet implementers.** Deferred: half the price of Opus per token, but the implementer now makes the design calls a spec used to make. It is the next lever if the trial runs over target.

## Consequences

- The pre-code gate found real defects by measuring before any code existed: a 1205 deadlock (5 of 5 runs), and delegated Entra tokens passing the partner policy. Defects like these now have to come from the tests a risk tag demands, or from the final review.
- Dev sees a batch's work only when the whole batch lands, up to about six tickets later than per-PR merging.
- Projects that never stacked PRs (Memerix) gain a batch branch per repository.
- Target: 12M weighted tokens per ticket or less, measured with `scripts/cost.py` over the first three batches.
