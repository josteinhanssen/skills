# deliver run

`/deliver <ADR path | ticket ids> [--into <branch>]` takes tickets to the integration branch and the environment it deploys to. This session is the orchestrator. It spawns, merges, verifies, deploys and talks to the user. It never builds and never reviews, and it keeps its own context small: it reads agent reports (short by contract) and script output, never transcripts or full logs.

Read the profile (`docs/agents/delivery-profile.md`) before step 1. Every branch name, command, label and path below comes from it; `--into` overrides the profile's integration branch for this run. Every path in an agent's brief is absolute. Spawn agents in the background, so two can run at once and the user can interrupt.

## 0. Resume or start

Run `scripts/state.py show`. With no open batch, start at step 1.

An open batch belongs to the session that started it, and `show` prints that owner. If the owner is another session, or none is recorded, that session may still be running the batch, for example watching a deploy. Ask the user once whether it has stopped. Only on a yes, run `scripts/state.py batch claim` and resume. Otherwise leave the batch alone; `state.py` refuses this session's writes to it anyway.

Resuming:

- A ticket whose agent the agent list (`ListAgents`) shows as running is left alone.
- A ticket in `building` whose agent is gone is respawned once, from the ticket and its worktree as it stands. The brief says the worktree holds earlier work; it never resets, cleans or checks out.
- A batch in `final-review`, `fixing`, `delivering` or `closing` continues from that step.

A new batch starts only when no batch is open. To start one while an older one is open, claim the older one as above, finish it from where it stands through its close (step 7.6), then start at step 1.

## 1. Budget

Read plan usage: in the desktop app, the session-management `get_usage` tool; elsewhere there is no reading, and the budget is a ticket count. Tell the user, in one message:

- the tickets and how they will batch (step 2),
- the weekly percentage used now,
- the estimate: tickets times the average weekly percentage per ticket recorded in `.deliver/costs.md`, or "no history yet" on the first batch,
- a proposed cap: the weekly reading at which no new ticket starts, written next to the current one ("now 91%, cap 97%").

This is the one question every run asks. The cap stops new tickets only. Once tickets are merged into the batch branch, the final review, the fix round and delivery run to the end, because stopping there leaves reviewed code undelivered; propose a cap that leaves room for them. When the answer can't be a reading (at or below the current one, or past 100), record your proposed cap and say so. Record `state.py batch set weeklyAtStart=<n> weeklyCap=<n>`, plus any consent the profile asks for in the answer (for example `mergeConsent=yes`). After every ticket, read usage again and record `weeklyAtEnd` on the ticket. At or above the cap, let the running tickets finish, start no new one, and take the tickets merged so far through steps 5 to 7. The rest stay queued for a later run. The batch's own end reading is taken once, at green CI (step 7.2).

The 5-hour window needs no handling: with `autoContinueAtUsageLimit` on (setup checks it), Claude Code waits for the reset and continues.

## 2. Intake: tickets against the bar

Read every ticket from the tracker. A ticket is ready when it has:

- what is true once it is done, in a sentence or two;
- acceptance criteria as observable behaviour;
- its blocking edges;
- exactly one repository, and the areas it touches;
- risk tags from the profile's list (auth, concurrency, migration, data loss) where they apply, or none;
- what is out of scope;
- a link to the ADR;
- an estimated size of about 400 changed production lines or less. Tests and generated files don't count: a ticket that needs a large test suite is not oversized for it.

Fix what you can in the tracker yourself: add missing risk tags, split a two-repository ticket into one per repository with a blocking edge (backend first), split an oversized ticket into slices with blocking edges, add the ADR link, and comment on each ticket what you changed. Stop and ask only when a fix needs a decision the ADR does not make.

Group the ready tickets into batches in blocking order. A batch closes at 6 tickets or about 2,500 production lines across its repositories, whichever comes first, so the final review can read all of it. Only the first batch is started; the next one starts after the first is delivered.

Write `.deliver/<slug>/tickets.md`: for each ticket, the id, title, repository, risk tags, estimated production lines, acceptance criteria and out-of-scope lines, copied from the tracker. Agents read this file, not the tracker.

Start `.deliver/<slug>/carry.md`, the carry list. It holds what the batch has to act on that no diff shows: follow-ups that a handoff, the grilling or an earlier batch left for this work, and facts an earlier measurement proved. One numbered line per item, ending in where it goes: a ticket in this batch (copy the item into that ticket's section of `tickets.md` too), or `outside` for the final review to rule on. Items are added as tickets finish (step 4.2) and closed at step 5.3.

## 3. Start the batch

For each repository in the batch:

```
git -C <repo> fetch origin <into>
git -C <repo> branch <batch-branch> origin/<into>
git -C <repo> push -u origin <batch-branch>
git -C <repo> worktree add <scratch-worktree> <batch-branch>
```

The scratch worktree is the orchestrator's own; ticket merges and checks happen there. Then:

```
scripts/state.py init --slug <slug> --adr <adr-path>
scripts/state.py repo <name> set path=<repo> into=<into> batchBranch=<batch-branch> baseHead=<sha> scratch=<scratch-worktree>
scripts/state.py ticket <id> set repo=<name> phase=queued blockedBy=[...] estimate=<production lines>
scripts/state.py batch set phase=building
```

`.deliver/` sits at the workspace root the profile names and is never committed. `init` records this session as the batch's owner and stores the ADR path as an absolute path; `cost.py` finds this session's transcripts from the agent ids in state, so `init` needs no session id. `init` moves a delivered batch's state file, or one written by deliver-v1, into `.deliver/archive/`, and refuses while a batch is open.

## 4. Per ticket

Start a ticket when everything it is blocked by is merged into the batch branch. Run at most two at once, and a second one only when neither blocks the other and they touch different repositories or clearly separate areas.

1. **Spawn the implementer** (`deliver-implementer`, in the background). The brief carries only:
   - the ticket id, and its section of `tickets.md` as the path and line range;
   - the ADR path and the carry list's path;
   - the repository, the ticket branch name from the profile's pattern, and the batch branch and its current head to branch from;
   - the worktree path and ports from the profile's sandbox conventions;
   - a database, assigned outright, when the ticket is tagged concurrency or migration or adds or edits a database-backed test (the profile says which tests those are). Never write "if you need one";
   - the ticket building alongside it, if any, and the areas that one touches.

   Record `ticket <id> set agent=<id> phase=building branch=<b> worktree=<w>` and move the ticket to the tracker's in-progress state.
2. **On DONE**, check the report's risk checks: an answer for each of the ticket's risk tags, and for inputs, existing paths and reuse. When one is missing, resume the implementer once for it (`SendMessage` to its agent id). Add each out-of-scope note to the carry list with the target the implementer named. A note for a later ticket in this batch also goes into that ticket's section of `tickets.md` and its brief.
3. **Merge into the batch branch**: `scripts/merge-ticket.sh --scratch <scratch-worktree> --ticket-branch <b> --ticket <id> --title "<title>" --estimate <n> --check "<profile unit command>" ...`. It merges with a merge commit, runs `verify-head.sh`, runs the checks only when the batch head moved since the ticket branched, pushes the batch branch, and prints the ticket's actual size. Exit 10 means a conflict: resume the implementer to merge the batch head into its branch and resolve, then run the script again. Exit 11 means a check failed on the merged head: resume the implementer with the failing command's tail.
4. **After the merge**: `scripts/sweep.py --path <repo> --ticket <b> --merged-into <batch-branch>` removes the worktree and the local ticket branch. Move the ticket to the tracker's in-review state with a comment: its Decisions and its risk checks, from the commit message. Record `phase=merged head=<sha> prodLines=<n>` and the usage reading (step 1).

   From here the batch bound (step 2) counts actual lines: the merged tickets' `prodLines` plus the estimates of those not yet started. When that passes the bound, the tickets not yet started wait for the next batch. Say so in your next message to the user; it is not a stop.

**BLOCKED from an implementer.** If the ADR, `tickets.md` or the grilling in this session answers it, answer by `SendMessage` and add the answer to the ticket as a comment. If not, it is a stop (step 8).

**Liveness.** Implementers run in the background; you are notified when they return. Past the profile's silence threshold, check the agent list; respawn once, only when it shows the agent not running.

**Reports that come back.** The harness can deliver a finished agent's report a second time, hours later, as a hand-back message or a task notification. When that report's step has already moved on, note it in one line and make no tool call.

## 5. Final review

When every ticket in the batch is merged:

1. In each scratch worktree: `git fetch origin <into> && git merge --no-ff origin/<into>`. On a conflict, `git merge --abort` and give it to the fixer (step 6) before anything else. Run the profile's full test rung once per repository. Where the profile names database-backed tests, the rung includes them: create the batch database from the profile's naming, migrate it at this head, and set the profile's switch for the run. Tests the rung skips count as not run, and the batch PR says so. Record `batch set phase=final-review` and each repository's `reviewedHead`.
2. Spawn the correctness reviewer and the quality reviewer in parallel (`deliver-correctness-reviewer`, `deliver-quality-reviewer`). Each gets: `tickets.md`, the ADR path, the carry list, and per repository the path, `baseHead` and `reviewedHead`. The correctness reviewer also gets its worktree path, port and database from the profile's sandbox conventions. Record their ids as `batch set 'reviewers={"correctness": "<id>", "quality": "<id>"}'`. Each returns its findings as its final message. Save each with `scripts/save-report.py --agent <id> --heading "# Correctness findings" --out .deliver/<slug>/findings-correctness.md`, and with `"# Quality findings"` to `findings-quality.md`; never retype a report. The fixer reads those files.
3. File every Follow-up finding as a new ticket in the tracker's backlog, linked to the ADR, and record the ids under `batch set followUps=[...]`. Then close the carry list: end each item's line with the reviewers' ruling (resolved in a commit, or dropped and why). File each item they ruled a follow-up, or didn't rule on, the same way, and end its line with the new ticket's id. No item stays open past this step.
4. With no Blocking or Should-fix findings and no Nits worth a commit, go to step 7.

## 6. The fix round

Spawn one fixer (`deliver-fixer`) with both findings files, the ADR path, `tickets.md`, and per repository the path, the batch head, and a fix branch and worktree of its own from the profile's patterns. Git will not check out the batch branch in a second worktree while your scratch worktree holds it, so the fixer works on its fix branch and never pushes. It fixes Blocking, Should-fix and Nit findings in the batch's own code, runs the tests the profile names, commits, and reports per finding: fixed (with sha) or disputed (with the reason). Record `batch set 'fixer=["<id>"]'`, and add to that list every later fixer this batch spawns.

Then, yourself:

- In each scratch worktree, `git merge --ff-only <fix branch>` and push the batch branch; `scripts/sweep.py --path <repo> --ticket <fix branch> --merged-into <batch-branch>` removes the fixer's worktree and branch.
- `scripts/verify-merge.py --repo <path> --delta <reviewedHead> <new head>`: list the delta and read every hunk against the finding that asked for it.
- A disputed finding: decide it from the findings file and the fixer's reason. If deciding it would change the ADR, it is a stop.
- If the review had any Blocking finding, spawn one confirm reviewer, of the axis that raised it, on the delta only (`--confirm` in its brief, with the earlier findings file). Record it with `batch set 'confirm=["<id>"]'`, and save its findings with `save-report.py` to `findings-<axis>-confirm.md`. Otherwise no reviewer sees the delta.
- Run the profile's unit rung in the scratch worktree, and the database-backed tests again when step 5.1 ran them. Record the new `reviewedHead`, and `batch set phase=delivering`.

The fixer is also who you spawn for a conflict in step 5.1, a failing CI run on the batch PR, and a deploy that fails for a code reason. Each of those gets one attempt.

## 7. Deliver

Per repository, in the profile's order (backend before frontend):

1. Open the batch PR from the batch branch into the integration branch with the profile's command. Description: what each ticket did and its Decisions, the final review's summary (findings fixed, disputed, filed as follow-ups), which database-backed tests ran, and the tickets it closes. When the Decisions don't fit the profile's description limit, link each ticket's tracker comment from step 4.4 instead. With a squash strategy the description becomes the commit message on the integration branch and the ticket commits leave its history, so the description must stand on its own. Record `repo <name> set pr=<id>`.
2. Wait for CI and the required policy builds with a background shell loop on the profile's PR status command, never by polling in turns. A failure gets one fixer attempt, then it is a stop. When the last repository's CI is green, read usage and `batch set weeklyAtEnd=<n>`. The batch's own work ends there; the waits after it are the user's, so nothing later overwrites the reading.
3. Vote as the profile allows (the creator's vote, when the policy counts it) and complete the PR with the profile's batch strategy, merge commit or squash. Claude Code's permission check may refuse your own vote or completion as self-approval, whatever consent the state records. Don't look for another way to approve: stop (step 8). The stop message starts with the profile's by-hand completion (the fields to set in the host's completion dialog), then gives the PR link. Continue at 7.4 when the user says it is merged.
4. `scripts/verify-merge.py --repo <path> --reviewed <reviewedHead> --merged <integration head>`: the merged tree must equal the reviewed tree, or be the clean merge of it onto a target that moved.
5. Deploy per the profile: watch the automatic deploy by commit, or queue it with the profile's commands and watch each run by id; then run the profile's after-deploy steps. A failure: read the run's log tail once; a code cause gets one fixer attempt and a new batch PR from the fix; a second failure is a stop.
6. **The close**, once per batch, after the last repository's deploy: `scripts/state.py batch claim --from delivering --to closing`. If the claim fails, another session is closing this batch: stop and tell the user. Otherwise:
   - per repository, `scripts/sweep.py --path <repo> --host <host> ... --ticket <batch-branch>` removes the scratch worktree and the batch branch, local and remote. `git -C <repo> worktree list` shows any reviewer worktree left behind (the profile's pattern); `scripts/sweep.py --path <repo> --worktree <path>` removes it;
   - drop the batch database and every ticket, fixer and reviewer database this batch's briefs assigned;
   - move every ticket to the tracker's done state with a comment (the merge commit, the deploy run);
   - `batch set phase=delivered`, run `scripts/cost.py --batch <slug> --summary-row` and append its row to `.deliver/costs.md`.

If another batch is waiting, go to step 3 with it; the budget from step 1 still holds.

In tracker text and PR descriptions, write slugs and branch names in backticks: the tracker may turn a bare `ate-488-b2` into a link to ATE-488.

## 8. Stops

Stop and ask the user only for:

- a product or scope decision that the ADR, `tickets.md` and the grilling do not answer;
- anything past the integration branch, anything touching secrets, or a write to a shared database (the user runs guarded scripts);
- a finding or dispute whose resolution would change the ADR;
- a CI run or deploy that fails again after its one fix attempt;
- a vote or PR completion the permission check refuses (step 7.3);
- a batch another session owns (step 0) or is closing (step 7.6);
- the weekly cap from step 1.

Everything else you decide, record in the tracker or the PR description, and continue. When you stop, say what is decided, what the options are, and your recommendation, in one message.

## Output at the end

A table per batch: ticket, repository, production lines against the estimate, merged head; the batch PRs and deploy runs; follow-ups filed; the cost row; the weekly percentage used.

## State keys

`scripts/state.py` accepts any key; `status` and `cost.py` read these:

| Scope | Keys |
|---|---|
| batch | `slug`, `adr`, `phase` (`building`, `final-review`, `fixing`, `delivering`, `closing`, `delivered`, `paused`), `owner` (the session id; set by `init` and `batch claim`), `startedAt`, `closedAt`, `sessionDir`, `sessionJsonl`, `weeklyAtStart`, `weeklyCap`, `weeklyAtEnd` (at green CI), `mergeConsent` (`yes` when the profile makes a vote depend on it), `reviewers` (`{"correctness": id, "quality": id}`), `fixer` (list), `confirm` (list), `followUps` (list) |
| repo | `path`, `into`, `batchBranch`, `baseHead`, `scratch`, `reviewedHead`, `pr`, `mergedHead`, `deployRuns` (list) |
| ticket | `repo`, `phase` (`queued`, `building`, `merged`, `blocked`), `blockedBy` (list), `estimate`, `branch`, `worktree`, `agent`, `head`, `prodLines`, `weeklyAtEnd`, `respawns` |

Record every agent id the moment you have it; an id missing from state lands in `cost.py`'s unassigned row. State files from batches before the ticket reviewer was dropped also hold `reviewer` and `flags` on tickets; `cost.py` still reads `reviewer`.
