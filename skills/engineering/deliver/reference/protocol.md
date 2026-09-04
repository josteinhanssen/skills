# The orchestrator and agent contract

Read this before spawning any agent from `run` or `close`. It is the whole contract; briefs only add the ticket, the spec path, the sandbox assignment and profile extracts.

## Files

| File | Owner | Purpose |
|---|---|---|
| `.deliver/state.json` | orchestrator, via `scripts/state.py` | per ticket: spec path, PR ids, agent ids, phase, head, grants, last report path, review rounds, rulings; per batch: base branch, integration head, run-of-record figures |
| `.deliver/reports/<agent-id>-<n>.md` | agent | the agent's turn-end report, verbatim; the orchestrator reads this, never the transcript |
| `.deliver/rulings/<ticket>.md` | judge, appended by the orchestrator into the spec | every ruling made after the spec was approved |
| the delivery log (path in the profile) | orchestrator | human-readable state of record, appended per event |
| `docs/agents/delivery-profile.md` | `setup` | the project's specifics |

`.deliver/` is committed except `reports/`, which is ignored. The state file is the source of truth for `status` and for a cold resume: on a fresh session, `run` reads it, lists every ticket not yet merged, checks whether each agent is alive, and respawns from the spec and the last report where it is not.

## Roles

Spawn only from the installed templates in `.claude/agents/` (`deliver-planner`, `deliver-plan-reviewer`, `deliver-implementer`, `deliver-implementer-escalation`, `deliver-reviewer-standards`, `deliver-reviewer-spec`, `deliver-judge`). The orchestrator is the session running `/deliver run` or `/deliver close`; it never implements and never reviews.

Reviewers and the judge are spawned with `fork_turns: "none"` and receive only: repository path, PR id, base and head refs, the changed-file list, the spec path, the implementer's totals, and for the judge the one question. They never receive the implementation transcript.

## Turn-end protocol

Every agent ends every turn with exactly one report, written to its report file and returned as its final message:

- `READY-FOR-RUN` (implementer): work, targeted tests, mutation proofs, bookkeeping and self-review are done; it needs a grant for an exclusive resource named in the spec before it can finish. Includes: branch, head, what ran and its totals, which resource and why.
- `READY-TO-MERGE` (implementer): PR id and head, reviewer state (rounds, resolved counts), the totals the spec's acceptance checks require, files touched, deviations from the spec, anything reported but not fixed. Nothing is claimed that was not run on the final head.
- `BLOCKED` (any role): the concrete decision needed, what was tried, the options with a recommendation. Never a question that the spec already answers.
- `VERDICT` (reviewers, plan-reviewer): findings under fixed headings (Blocking, Should-fix, Nit, Verified clean), each with file and line, under 400 words; the same headings on incremental passes with "closed" or "still open" per earlier finding.
- `RULING` (judge): the decision, the reason in two sentences, and the exact text to append to the spec.

An agent never idle-waits on the orchestrator. It ends the turn and is resumed with context intact, or respawned from files if the session died.

## Exclusive resources and grants

The profile lists resources that must not run concurrently (an authoritative browser matrix, an armed backend suite, a shared database migration). An agent may not use one without a grant. A grant covers one run, not a phase; a re-run is a new request. While a grant is held, other agents defer multi-target runs of the same kind and continue with single-target checks.

The orchestrator runs the authoritative verification itself, on the merged head, at the profile's cadence. Agents run the cheap rung freely and the targeted rung only on what their spec names.

## Review rounds

1. After the first push, the orchestrator (or the implementer, if the profile says so) spawns the Standards and the Spec reviewer with refs only.
2. The implementer takes every valid finding, replies with a reason to invalid ones, pushes once, and sends both reviewers the incremental range.
3. After each reviewer's second full pass, the orchestrator declares the closing round: one push, confirm-only passes. Trivial residue (unused imports, docstrings, counts) is pushed without another round and the orchestrator diffs that delta at merge.
4. Reviewer disagreement goes to the judge, not to the implementer.
5. A finding that needs a design decision the spec did not make is a BLOCKED, not a fix.

## Mechanical checks before review

Run and record on the head before spawning reviewers; a reviewer's time is not spent on what a script proves:

- the profile's typechecks and unit suite
- the profile's invariants (budgets, counters, parity guards)
- conflict-marker grep on the head (`scripts/verify-head.sh`)
- for a change that removes tests: the listed-title diff base-to-head, reconciled with the spec's migration map
- unused declarations in the touched files, with whatever the profile names as the detector
- one mutation proof per claim the spec lists, restored by reversing the edit and shown byte-identical

## Limits

- Review passes: two full, then closing. Rounds beyond that mean the spec was wrong; the orchestrator sends the ticket back to `spec`.
- Rulings per ticket: two, then back to `plan`.
- Respawns after a dead session: one, from the spec and the last report.
- A small-model implementer whose PR fails review on design grounds gets the ruling first; the escalation template is used only when the ruling itself needs design judgment the spec cannot express as an instruction.

## Sandbox conventions

Each implementer works in its own worktree from the profile's pattern, on a fresh branch from the base the orchestrator names, with the ports, databases and cache directories the brief assigns. It never touches another worktree, never installs dependencies through a shared symlink, stages explicit paths only, and leaves a clean tree at the pushed head when it stands down. The orchestrator removes the worktree and both branches after verifying the merge.
