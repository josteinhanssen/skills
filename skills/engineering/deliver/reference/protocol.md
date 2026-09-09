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
- `READY-TO-MERGE` (implementer): PR id and head, reviewer state (rounds, resolved counts, and the agent id of every reviewer it spawned, per pass, so the orchestrator can record them for cost attribution), the totals the spec's acceptance checks require, files touched, deviations from the spec, anything reported but not fixed. Nothing is claimed that was not run on the final head.
- `BLOCKED` (any role): the concrete decision needed, what was tried, the options with a recommendation. Never a question that the spec already answers.
- `VERDICT` (reviewers, plan-reviewer): findings under fixed headings (Blocking, Should-fix, Nit, Verified clean), each with file and line, under 400 words; the same headings on incremental passes with "closed" or "still open" per earlier finding.
- `RULING` (judge): the decision, the reason in two sentences, and the exact text to append to the spec.

An agent never idle-waits on the orchestrator. It ends the turn and is resumed with context intact, or respawned from files if the session died. An implementer that has spawned reviewers may end its turn; the harness wakes it when a child completes, so waiting on reviewers by ending the turn is allowed.

Liveness is read from the agent list (the harness's `ListAgents`), never from transcript files: a running agent's task output file stays empty until it ends. Respawn only an agent the list shows as not running, and hand its worktree over as it stands; a respawn brief never resets, checks out or cleans a worktree (a live predecessor's staged work was destroyed that way once).

## Exclusive resources and grants

The profile lists resources that must not run concurrently (an authoritative browser matrix, an armed backend suite, a shared database migration). An agent may not use one without a grant. A grant covers one run, not a phase; a re-run is a new request. While a grant is held, other agents defer multi-target runs of the same kind and continue with single-target checks.

Grants travel as files, for the same reason verdicts do: the orchestrator may have no channel to resume an agent. `scripts/state.py grant <resource> <agent-id>` records the grant in the state file and writes `.deliver/grants/<resource>`; the agent that reported READY-FOR-RUN waits on that file with `scripts/wait-grant.sh <resource> <agent-id>` (bounded, 45 minutes by default) instead of ending its turn and hoping for a GO. `state.py release <resource>` removes the file when the agent's report shows the run is done. An implementer that runs an exclusive resource without a grant file naming it has deviated, and says so in its report.

When the resource is free at spawn time, the orchestrator grants it in the brief (`state.py grant` before the spawn, one run) and tells the implementer to delete the grant file the moment the run ends; an agent waiting in-turn on a grant file cannot notify the orchestrator, so a grant issued later reaches it only through the file. While a grant file for a machine-wide resource (a contention probe, an armed suite) exists, no other agent starts a multi-file run of the same kind.

A resource that several implementers of one batch each need once, and that the orchestrator would otherwise hand out serially, is better self-serialised by the runners than granted: the profile names a lock directory (`.deliver/locks/<resource>` at the workspace root), the runner creates it atomically with `mkdir`, writes its agent id and the UTC start time into `holder`, runs once, and removes the directory when the run ends; a runner that finds it present waits (poll every 30 s, bounded like a grant) or runs single targets, and never removes another agent's lock. The orchestrator breaks a lock only when it is older than the profile's staleness bound and no process of that run exists. Reason: a grant issued after spawn reaches an in-turn waiter only through a file the orchestrator has to write at the right moment, which it cannot see; a lock the runners manage among themselves needs no orchestrator turn at all. Grants stay for resources the orchestrator must hand out one run at a time in a chosen order (a matrix slot, a migration).

The orchestrator runs the authoritative verification itself, on the merged head, at the profile's cadence. Agents run the cheap rung freely and the targeted rung only on what their spec names.

## Review rounds

Planning phase (plan and spec): one review pass. The plan-reviewer returns one VERDICT; the planner applies every finding; the orchestrator verifies closure by reading the planner's delta against the findings (a cheap diff, not a second review). A confirm pass on the delta is spawned only when the first pass had a Blocking finding. This replaced two passes after the first trial showed the spec phase costing more than the implementation on small tickets.

Implementation phase (PR review):

0. Reviewer verdicts travel as files, never only as notifications. A reviewer writes its VERDICT to `.deliver/reports/<ticket>-<axis>-<pass>.md` before returning it; the implementer waits with `scripts/report.py --wait` on those paths (or polls the directory) instead of idling on a notification that may reach the orchestrator rather than the implementer. A completion notice that says only "waiting for the reviewers" is a defect in the brief, not a state.
1. After the first push, the orchestrator (or the implementer, if the profile says so) spawns the Standards and the Spec reviewer with refs only.
2. The implementer takes every valid finding, replies with a reason to invalid ones, pushes once, and spawns fresh reviewers for the second full pass with the first verdict file and the incremental range. A ticket whose spec marks `volume: large` (see Sizing) gets one full pass per axis; a second pass only when the first raised a Blocking or Should-fix finding.
3. The closing round belongs to the orchestrator, never to a third reviewer spawn. After the last full pass the implementer pushes once (the applied findings plus any trivial residue: unused imports, docstrings, counts) and reports READY-TO-MERGE. The orchestrator diffs the delta since the last verdict head (`scripts/pre-merge.py ... --reviewed-head <ref>`), merges when the delta is trivial (test-only, comment-only, bookkeeping, or exactly the edits the verdicts asked for), and spawns one confirm reviewer on the affected axis only when it is not. Implementers do not spawn confirm-only reviewers.
4. Reviewer disagreement goes to the judge, not to the implementer.
5. A finding that needs a design decision the spec did not make is a BLOCKED, not a fix.
6. A BLOCKED whose answer is a wording defect in an acceptance check or a bookkeeping sentence (a command that cannot produce its stated pass shape, a count that contradicts its own block) is ruled by the orchestrator as a numbered ruling appended to the spec and to `.deliver/rulings/<ticket>.md`, without the judge; anything that touches design, scope or coverage still goes to the judge.

Orchestrator hotfixes stop at wording the orchestrator can verify by reading: an anchor, a citation, a pass shape, a check's command, a ruling's cross-reference, a count the file list already states. They never write a fixture's shape, a test table, a type declaration, a probe's mechanism or a number the orchestrator would have to recompute — those go back to the planner even when the reviewer has spelled out the fix, because the planner re-measures and the orchestrator does not. Measured on handoff-and-calendar (2026-09-09): two orchestrator hotfixes on specs each earned a fresh Blocking (a grep term that spanned a line break; a fixture envelope with its members in the wrong object and every dependent count left stale), each costing a confirm pass and a planner round that a planner round alone would have cost once.

## Mechanical checks before review

Run and record on the head before spawning reviewers; a reviewer's time is not spent on what a script proves:

- the profile's typechecks and unit suite
- the profile's invariants (budgets, counters, parity guards)
- conflict-marker grep on the head (`scripts/verify-head.sh`)
- for a change that removes tests: the listed-title diff base-to-head, reconciled with the spec's migration map
- unused declarations in the touched files, with whatever the profile names as the detector
- one mutation proof per claim the spec lists, restored by reversing the edit and shown byte-identical

## Limits

- PR review passes: two full (one for a `volume: large` ticket), then the orchestrator's closing diff. Rounds beyond that mean the spec was wrong; the orchestrator sends the ticket back to `spec`.
- Plan and spec review: one pass, plus a confirm pass on the delta only after a Blocking finding.
- Rulings per ticket: two, then back to `plan`.
- Respawns after a dead session: one, from the spec and the last report.
- A small-model implementer whose PR fails review on design grounds gets the ruling first; the escalation template is used only when the ruling itself needs design judgment the spec cannot express as an instruction.

## Sizing

Two independent marks per ticket, both set by the planner and carried into the spec:

- **Model** (`small` / `large`) follows the ruling count and the blast radius: the work is typing, or the work is design.
- **Volume** (`volume: large` or nothing) follows the estimated diff, in files and changed lines, against the profile's threshold (default: more than 300 changed lines or more than 8 files). Volume sets the PR review shape: a large-volume ticket gets one full review pass per axis, and the mechanical checks (the pre-merge script, the detector, the mutation probes, the invariants) carry the rest. A 1,197-line sweep across 67 sites with zero findings in six reviewer spawns is what this mark exists for.

## Sandbox conventions

Each implementer works in its own worktree from the profile's pattern, on a fresh branch from the base the orchestrator names, with the ports, databases and cache directories the brief assigns. It never touches another worktree, never installs dependencies through a shared symlink, stages explicit paths only, and leaves a clean tree at the pushed head when it stands down. The orchestrator removes the worktree and both branches after verifying the merge.

Reviewers and planners never run a git command that changes a working tree they did not create: no `checkout`, `switch`, `reset`, `stash`, `clean` or `restore` in the primary checkout or another agent's worktree. They read with `git show <ref>:<path>`, `git grep <ref>`, `git diff <a> <b>`, or in a `git archive` scratch tree of their own.

Planners and reviewers that need a compiled base (to run a compiler flag, a listing, a probe) get a scratch tree of their own, named after the agent, or treat a shared base tree as read-only: verify with `git show <ref>:<path>` and `git grep <ref>`, never by editing the shared tree. Two planners sharing one scratch tree in the same batch produced a stray probe file that the other planner had to revert; a measurement taken from a tree another agent is writing to is not a measurement.
