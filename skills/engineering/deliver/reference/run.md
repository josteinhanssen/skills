# deliver run

`/deliver <ADR path | ticket ids> [--into <branch>]` takes tickets to the integration branch and the environment it deploys to. This session is the orchestrator. It spawns, merges, verifies, deploys and talks to the user. It never builds and never reviews, and it keeps its own context small: it reads agent reports (short by contract) and script output, never transcripts or full logs.

Read the profile (`docs/agents/delivery-profile.md`) before step 1. Every branch name, command, label and path below comes from it; `--into` overrides the profile's integration branch for this run. Every path in an agent's brief is absolute. Spawn agents in the background, so two can run at once and the user can interrupt.

## 0. Resume or start

Run `scripts/state.py show`. If a batch is open, this is a resume:

- A ticket whose agent the agent list (`ListAgents`) shows as running is left alone.
- A ticket in `building` or `answering` whose agent is gone is respawned once, from the ticket and its worktree as it stands. The brief says the worktree holds earlier work; it never resets, cleans or checks out.
- A batch in `final-review`, `fixing` or `delivering` continues from that step.

Otherwise start at step 1.

## 1. Budget

Read plan usage: in the desktop app, the session-management `get_usage` tool; elsewhere there is no reading, and the budget is a ticket count. Tell the user, in one message:

- the tickets and how they will batch (step 2),
- the weekly percentage used now,
- the estimate: tickets times the average weekly percentage per ticket recorded in `.deliver/costs.md`, or "no history yet" on the first batch,
- a proposed cap: the weekly percentage at which no new ticket starts.

This is the one question every run asks. The cap stops new tickets only. Once tickets are merged into the batch branch, the final review, the fix round and delivery run to the end, because stopping there leaves reviewed code undelivered; propose a cap that leaves room for them. Record `state.py batch set weeklyAtStart=<n> weeklyCap=<n>`, plus any consent the profile asks for in the answer (for example `mergeConsent=yes`). After every ticket, read usage again and record `weeklyAtEnd` on the ticket. At or above the cap, let the running tickets finish, start no new one, and take the tickets merged so far through steps 5 to 7. The rest stay queued for a later run.

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
- an estimated size of about 400 changed production lines or less. Tests don't count: a ticket that needs a large test suite is not oversized for it.

Fix what you can in the tracker yourself: add missing risk tags, split a two-repository ticket into one per repository with a blocking edge (backend first), split an oversized ticket into slices with blocking edges, add the ADR link, and comment on each ticket what you changed. Stop and ask only when a fix needs a decision the ADR does not make.

Group the ready tickets into batches in blocking order. A batch closes at 6 tickets or about 2,500 estimated production lines across its repositories, whichever comes first, so the final review can read all of it. Only the first batch is started; the next one starts after the first is delivered.

Write `.deliver/<slug>/tickets.md`: for each ticket, the id, title, repository, risk tags, acceptance criteria and out-of-scope lines, copied from the tracker. Agents read this file, not the tracker.

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
scripts/state.py ticket <id> set repo=<name> phase=queued blockedBy=[...]
scripts/state.py batch set phase=building
```

`.deliver/` sits at the workspace root the profile names and is never committed. `init` stores the ADR path as an absolute path; `cost.py` finds this session's transcripts from the agent ids in state, so `init` needs no session id. `init` moves a delivered batch's state file, or one written by deliver-v1, into `.deliver/archive/`, and refuses while a batch is open.

## 4. Per ticket

Start a ticket when everything it is blocked by is merged into the batch branch. Run at most two at once, and a second one only when neither blocks the other and they touch different repositories or clearly separate areas.

1. **Spawn the implementer** (`deliver-implementer`, in the background). The brief carries only: the ticket id; its section of `tickets.md`, pasted; the ADR path; the repository; the ticket branch name from the profile's pattern; the batch branch and its current head to branch from; the worktree path, ports and database from the profile's sandbox conventions; the flag file path (`.deliver/<slug>/flags/<ticket>.md`). Record `ticket <id> set agent=<id> phase=building branch=<b> worktree=<w>` and move the ticket to the tracker's in-progress state.
2. **On DONE**, spawn the ticket reviewer (`deliver-ticket-reviewer`) with the ticket's section of `tickets.md`, the ADR path, the repository, the base (the batch head the ticket branched from), the implementer's head, and the flag file path. Record `reviewer=<id> phase=flagged`. If it reports that the harness refused its write, write the flag file from its report.
3. **On the reviewer's return**: with no flags, go to 4. With flags, resume the same implementer (`SendMessage` to its agent id): "Your flags are in <flag file>. Fix each one you can confirm with a test or a clear reading; answer the rest on the flag's own line. Commit, then report DONE." Record `phase=answering`. There is no second ticket-review pass.
4. **Merge into the batch branch**: `scripts/merge-ticket.sh --scratch <scratch-worktree> --ticket-branch <b> --ticket <id> --title "<title>" --check "<profile unit command>" ...`. It merges with a merge commit, runs `verify-head.sh`, runs the checks only when the batch head moved since the ticket branched, and pushes the batch branch. Exit 10 means a conflict: resume the implementer to merge the batch head into its branch and resolve, then run the script again. Exit 11 means a check failed on the merged head: resume the implementer with the failing command's tail.
5. **After the merge**: `scripts/sweep.py --ticket <b> --merged-into <batch-branch> ...` removes the worktree and the local ticket branch. Move the ticket to the tracker's in-review state with a comment: its Decisions list (from the commit message) and its flags with their answers. Record `phase=merged head=<sha>` and the usage reading (step 1).

**BLOCKED from an implementer.** If the ADR, `tickets.md` or the grilling in this session answers it, answer by `SendMessage` and add the answer to the ticket as a comment. If not, it is a stop (step 8).

**Liveness.** Implementers run in the background; you are notified when they return. Past the profile's silence threshold, check the agent list; respawn once, only when it shows the agent not running.

## 5. Final review

When every ticket in the batch is merged:

1. In each scratch worktree: `git fetch origin <into> && git merge --no-ff origin/<into>`. On a conflict, `git merge --abort` and give it to the fixer (step 6) before anything else. Run the profile's full test rung once per repository. Record `batch set phase=final-review` and each repository's `reviewedHead`.
2. Spawn the correctness reviewer and the quality reviewer in parallel (`deliver-correctness-reviewer`, `deliver-quality-reviewer`). Each gets: `tickets.md`, the ADR path, the flag directory, and per repository the path, `baseHead` and `reviewedHead`. Record their ids under `batch set reviewers=...`. Each returns its findings as its final message, because the harness refuses report files from sub-agents. Save each one as it stands, with one write, to `.deliver/<slug>/findings-correctness.md` and `.deliver/<slug>/findings-quality.md`; the fixer reads those files.
3. File every Follow-up finding as a new ticket in the tracker's backlog, linked to the ADR, and record the ids under `batch set followUps=[...]`.
4. With no Blocking or Should-fix findings and no Nits worth a commit, go to step 7.

## 6. The fix round

Spawn one fixer (`deliver-fixer`) with both findings files, the ADR path, `tickets.md`, and per repository the path, the batch head, and a fix branch and worktree of its own from the profile's patterns. Git will not check out the batch branch in a second worktree while your scratch worktree holds it, so the fixer works on its fix branch and never pushes. It fixes Blocking, Should-fix and Nit findings in the batch's own code, runs the tests the profile names, commits, and reports per finding: fixed (with sha) or disputed (with the reason).

Then, yourself:

- In each scratch worktree, `git merge --ff-only <fix branch>` and push the batch branch; `scripts/sweep.py --ticket <fix branch> --merged-into <batch-branch> ...` removes the fixer's worktree and branch.
- `scripts/verify-merge.py --repo <path> --delta <reviewedHead> <new head>`: list the delta and read every hunk against the finding that asked for it.
- A disputed finding: decide it from the findings file and the fixer's reason. If deciding it would change the ADR, it is a stop.
- If the review had any Blocking finding, spawn one confirm reviewer, of the axis that raised it, on the delta only (`--confirm` in its brief, with the earlier findings file), and save its findings as `findings-<axis>-confirm.md`. Otherwise no reviewer sees the delta.
- Run the profile's unit rung in the scratch worktree, record the new `reviewedHead`, and `batch set phase=delivering`.

The fixer is also who you spawn for a conflict in step 5.1, a failing CI run on the batch PR, and a deploy that fails for a code reason. Each of those gets one attempt.

## 7. Deliver

Per repository, in the profile's order (backend before frontend):

1. Open the batch PR from the batch branch into the integration branch with the profile's command. Description: what each ticket did, its Decisions, the final review's summary (findings fixed, disputed, filed as follow-ups), and the tickets it closes. Record `repo <name> set pr=<id>`.
2. Wait for CI and the required policy builds with a background shell loop on the profile's PR status command, never by polling in turns. A failure gets one fixer attempt, then it is a stop.
3. Vote as the profile allows (the creator's vote, when the policy counts it) and complete the PR with the profile's batch strategy: a merge commit where the branch policy allows one, so each ticket's commit and Decisions stay on the integration branch; a squash where it only allows that, with every ticket's Decisions in the PR description. Claude Code's permission check may refuse your own vote or completion as self-approval, whatever consent the state records. Don't look for another way to approve: stop (step 8) with the PR link and the profile's by-hand completion (the option to pick in the host's completion dialog and the boxes to leave off), and continue at 7.4 when the user says it is merged.
4. `scripts/verify-merge.py --repo <path> --reviewed <reviewedHead> --merged <integration head>`: the merged tree must equal the reviewed tree, or be the clean merge of it onto a target that moved.
5. Deploy per the profile: watch the automatic deploy by commit, or queue it with the profile's commands and watch each run by id; then run the profile's after-deploy steps. A failure: read the run's log tail once; a code cause gets one fixer attempt and a new batch PR from the fix; a second failure is a stop.
6. `scripts/sweep.py --host <host> ... --ticket <batch-branch>` removes the scratch worktree and the batch branch, local and remote, once the PR is completed and the heads match.

Then move every ticket to the tracker's done state with a comment (the merge commit, the deploy run), read usage once more, `batch set weeklyAtEnd=<n> phase=delivered`, run `scripts/cost.py --batch <slug> --summary-row` and append its row to `.deliver/costs.md`. If another batch is waiting, go to step 3 with it; the budget from step 1 still holds.

## 8. Stops

Stop and ask the user only for:

- a product or scope decision that the ADR, `tickets.md` and the grilling do not answer;
- anything past the integration branch, anything touching secrets, or a write to a shared database (the user runs guarded scripts);
- a finding or dispute whose resolution would change the ADR;
- a CI run or deploy that fails again after its one fix attempt;
- a vote or PR completion the permission check refuses (step 7.3);
- the weekly cap from step 1.

Everything else you decide, record in the tracker or the PR description, and continue. When you stop, say what is decided, what the options are, and your recommendation, in one message.

## Output at the end

A table per batch: ticket, repository, flags, merged head; the batch PRs and deploy runs; follow-ups filed; the cost row; the weekly percentage used.

## State keys

`scripts/state.py` accepts any key; `status` and `cost.py` read these:

| Scope | Keys |
|---|---|
| batch | `slug`, `adr`, `phase` (`building`, `final-review`, `fixing`, `delivering`, `delivered`, `paused`), `startedAt`, `closedAt`, `sessionDir`, `sessionJsonl`, `weeklyAtStart`, `weeklyCap`, `weeklyAtEnd`, `mergeConsent` (`yes` when the profile makes a vote depend on it), `reviewers` (`{"correctness": id, "quality": id}`), `fixer`, `confirm` (list), `followUps` (list) |
| repo | `path`, `into`, `batchBranch`, `baseHead`, `scratch`, `reviewedHead`, `pr`, `mergedHead`, `deployRuns` (list) |
| ticket | `repo`, `phase` (`queued`, `building`, `flagged`, `answering`, `merged`, `blocked`), `blockedBy` (list), `branch`, `worktree`, `agent`, `reviewer`, `head`, `flags`, `weeklyAtEnd`, `respawns` |

Record every agent id the moment you have it; an id missing from state lands in `cost.py`'s unassigned row.
