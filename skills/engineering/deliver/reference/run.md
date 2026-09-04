# deliver run

Orchestrates a batch of specced tickets to merged, verified PRs. This session is the orchestrator: it spawns, grants, routes, verifies, merges and logs. It never implements, never reviews, and keeps its own context small by reading report files and bounded summaries, never transcripts.

## 0. Resume or start

Read `.deliver/state.json`. If the batch exists, this is a resume: for every ticket not merged, check whether its agent is alive (a report file newer than the last state update, or a running task); respawn dead agents from the spec and their last report, once. Otherwise start: record the base branch and head, the batch slug, the tickets and their specs.

## 1. Schedule

From the plan: implement in blocking order, in parallel where files are disjoint, up to the profile's parallelism. Assign each implementer a sandbox from the profile's conventions (worktree path, port range, database name, cache directory) and record it in the state file. Tickets whose spec says `large` use the escalation template from the start.

## 2. Spawn

Brief each implementer with: the spec path, the base branch and head, the sandbox assignment, the profile extracts its template marks, the batch-wide rulings, and the sentence "the orchestrator may not be able to message you; resolve to READY-TO-MERGE on the written rulings and report BLOCKED only for a decision the spec cannot answer". Record the agent id.

## 3. React to reports

Every agent turn ends with a report file. On each:

- `READY-FOR-RUN`: if the requested resource is free, write the grant into the state file and resume the agent with `GO` and the one-run rule; otherwise queue it and resume the holder's successor when the holder reports.
- `READY-TO-MERGE`: run the merge checklist below.
- `BLOCKED`: spawn the judge with the spec and the one question; append the RULING to `.deliver/rulings/<ticket>.md` and to the spec's Rulings section; resume the implementer with the ruling. Second BLOCKED on the same ticket: back to `spec`.
- `VERDICT` from a reviewer that reaches the orchestrator instead of the implementer: relay it verbatim to the implementer with the round number.
- Silence past the profile's threshold: check liveness; respawn once.

## 4. Merge checklist

Before completing a PR:

1. Both reviewers have confirmed the final head, or the closing-round rule applies and the delta since the last confirmed head is trivial (diff it yourself; test-only and comment-only).
2. `scripts/verify-head.sh` on the PR head: conflict markers, the profile's invariants, the spec's cheap acceptance commands.
3. Production files changed are the ones the spec names; anything else is a deviation the report must have declared.
4. Complete the PR with the profile's merge strategy and command; then verify the merged head's content directly (the same script on the target branch head), never by ancestry.
5. Remove the worktree, the local branch and the remote branch with `scripts/sweep.py --ticket <id>`, after confirming no sibling symlinks into the worktree.
6. Delete the spec file on the base branch in the next housekeeping commit (or leave it to `close`), and comment on the tracker ticket with the merge commit, what was verified, and what was reported but not fixed.
7. Update the state file and append to the delivery log.

Announce the new base head to every running implementer whose spec shares a file with the merged one; others rebase at their READY-TO-MERGE.

## 5. Authoritative run cadence

Per the profile: after each merge, or once on the batch head before `close`. The orchestrator runs it itself in its own scratch worktree, with the profile's command, on a port and cache directory no agent uses, with the machine as quiet as the grant protocol can make it. Failures are discriminated before they are attributed: rerun the failing targets in isolation; contention is not a regression.

## 6. Hygiene while running

- Never read an agent's transcript; read its report file.
- Never run `npm install` or a dependency install through a shared symlink; the scratch worktree gets its own or a symlink to a directory no other worktree owns.
- Never remove a worktree another agent may still read (its reviewers can be mid-pass).
- Log every event with a timestamp in the delivery log; the log is what a cold resume reads first.

## Output at the end of `run`

The state table (ticket, PR, head, merged, rounds, rulings) and the list of follow-ups reported but not fixed, each with its ticket id.

## State keys the scripts read

`scripts/state.py ticket <id> set key=value ...` accepts any key, but `cost.py` and `status` attribute by these names only; use them exactly:

| Key | Set by | Read by |
|---|---|---|
| `spec`, `model`, `phase`, `pr`, `head`, `merged`, `sandbox`, `rounds`, `rulings`, `findingsAfterMerge` | orchestrator | `status`, `cost.py` (rounds, findings) |
| `agent` | orchestrator at spawn | `cost.py` as the implementation cost |
| `plannerAgents`, `reviewerAgents`, `judgeAgents`, `implementerAgents` (lists) | orchestrator when it spawns them, or from the READY-TO-MERGE report when the implementer spawned the reviewers | `cost.py` per phase |

Record reviewer ids the moment you learn them; an id missing from state lands in the unassigned bucket and the ticket's review cost reads as zero.

An invariant that reports FAILED with a log that has no result line (the runner started and stopped) is a broken run, not a failing test: rerun it once on the same head before treating it as a failure, and say in the log which it was.
