# deliver run

`/deliver <ADR path | ticket ids> [--into <branch>] [--model <role>=<model>] [--effort <role>=<effort>]` takes tickets to the integration branch and the environment it deploys to. This session is the orchestrator. It spawns, merges, verifies, deploys and talks to the user. It never builds and never reviews, and it keeps its own context small: it reads agent reports (short by contract) and script output, never transcripts or full logs.

Read the profile (`docs/agents/delivery-profile.md`) before step 1. Every branch name, command, label and path below comes from it; `--into` overrides the profile's integration branch for this run, and `--model` and `--effort` (each repeatable) a role's model or effort (see Models and efforts). Every path in an agent's brief is absolute. Every agent runs in a workflow (below), so two can run at once, the user can interrupt, and the batch shows in the background tasks.

**Tracker writes go through the clerk.** Read the tracker yourself, and hand every write (state moves, comments, new tickets) to the tracker clerk (`deliver-tracker-clerk`, on Haiku). A tracker's write tools can echo the whole issue back: about 2.5k tokens per state move in Linear, and in trial 2 those echoes were the largest thing in the orchestrator's context. Queue writes and hand them over at five points: the end of intake, after each ticket's merge (with the in-progress moves of tickets started since), step 5.3, the end of the fix round when it left anything to file (step 6), and the close. The brief names the write and search tools (step 0) and is a numbered list of complete writes, with the full text of every comment and new ticket, or the file that holds it. The clerk returns one line per write. Wait for its report whenever its list creates a ticket, since new tickets' ids go into `tickets.md`, state and `notes.md`; otherwise let it run in the background. Record each clerk's run id on `clerks`. The intake clerk runs before step 3 makes the new batch, so keep its run id in `notes.md` until step 3 records it. A failed write goes into the next clerk's list. If the clerk can't reach the tracker at all, make the writes yourself for the rest of the run and say so in your next message.

**Tracker offline.** When the user chooses to run without the tracker (step 0), they paste each ticket you need to read. A new ticket gets a provisional id, its parent's id with a suffix (`ATE-496-BE1`), which `tickets.md`, state, branches and databases use for the rest of the run. Every write goes into `.deliver/<slug>/tracker-queue.md` instead of to a clerk: numbered and complete, as a clerk's brief would be, with long comment text in files next to it. At the close, give the user the queue's path. When the tracker is back, a clerk makes the queue's writes, leaving out the state moves that a later move overtakes and replacing each provisional id with the real one, and the queue records which real id each provisional one became.

**Agents run in workflows.** Every agent this playbook spawns, the clerk included, runs in a Claude Code workflow for its spawn point. The user sees the batch in the background tasks as workflows named `deliver <slug> · <step>`, with one row per agent and its model. `/deliver` is the user's opt-in to the Workflow tool. To spawn:

1. `scripts/workflow.py render --slug <slug> --step "<step>" --phase <phase> --agent-type <role agent> [--agent-type ...]` writes the workflow's script and prints its path, then each role's model and effort. It writes those into the script, since a workflow agent otherwise runs on the session's.
2. Call Workflow with `scriptPath` set to that path and `args` set to `{"agents": [{"label": "<label>", "agentType": "<role agent>", "brief": "<brief>"}]}`, as a JSON object, not a string. The agents in one workflow start together.
3. Record the workflow's run id from the launch result at once, under the key the step names.

| Spawn | Step | Phase | Agents, as label |
|---|---|---|---|
| a ticket (4.1) | the ticket id | Build | `deliver-implementer`, as the ticket id |
| the final review (5.2) | `final review` | Final review | `deliver-correctness-reviewer` as `correctness`, `deliver-quality-reviewer` as `quality` |
| the fix round (6), or a fix for a conflict, CI or a deploy | `fix round`, `merge fix`, `CI fix`, `deploy fix` | Fix | `deliver-fixer` as `fixer` |
| the confirm pass (6) | `confirm` | Confirm | each axis's reviewer as `confirm-correctness` or `confirm-quality` |
| tracker writes | `tracker <n>` | Tracker | `deliver-tracker-clerk` as `clerk` |

Two tickets side by side are two workflows. A workflow notifies you once, when its last agent finishes, with `{label: final report}`; `null` means that agent ended without a report (see Liveness). `scripts/workflow.py agents <run id>` lists a workflow's agents with their ids and status: running, done, failed with its error, or killed.

A workflow agent can't be resumed: it isn't in `ListAgents`, and `SendMessage` can't reach it. Where this playbook goes back to an agent, launch a **continuation**: a fresh agent of the same role and label, in a new workflow whose step is the earlier one plus ` continued` (`ATE-543 continued`). Its brief is the brief the agent had, a line saying its worktree (or fix branch) holds the earlier work as it stands and is never reset, cleaned or checked out, and what to do: one thing (a missing risk check, a conflict, a failed check), or finish the work (a BLOCKED answer, an agent that failed or went silent). Its run id goes last on the same key. `state.py set` replaces a list, so write the whole list each time: `ticket <id> set 'runs=["<first>", "<continuation>"]'`. Save a report from the latest run on its key that ran its label. To reach an implementer while it builds, write to its inbox, `.deliver/<slug>/inbox/<ticket id>.md`; it reads the inbox before its last test run and again before it commits.

**Models and efforts.** A role runs on the model and effort in its agent's frontmatter (the default), unless the profile's Agents table changes them for the workspace or this run changes them for its batches. The run's changes come from `--model` and `--effort` on the command line, or from the user's answer in step 1; step 3 records them on the batch as `agentSettings`. The later layer wins, field by field, and `render` applies all three. `scripts/workflow.py settings [--slug <slug>]` prints what each role runs on and which layer each value came from. A role is `implementer`, `correctness-reviewer`, `quality-reviewer`, `fixer` or `tracker-clerk`. Never edit an installed agent's frontmatter to change one run: setup overwrites it, and every later run would inherit it.

## 0. Resume or start

Run `scripts/state.py show`. With no open batch, start at step 1.

Then, starting or resuming, load the tracker's tools with ToolSearch: the write and search tools the profile names and the ones you read with. A claude.ai connector's tool names carry an id that differs between Claude accounts (`mcp__<id>__save_issue`), so when the profile's names aren't found, search for the tools' own names (`save_issue`). If one server offers them all, use its full names for this run and in every clerk brief, update the profile's Write tools line and the clerk agent's Profile section to them, and tell the user. If none does, stop: the tracker isn't connected to this account, and only the user can connect it. The user may instead choose to run with the tracker offline (below).

Then, starting or resuming, check the role agents with `scripts/agents.py check`. It exits 1 when an agent in `.claude/agents/` no longer matches the installed skill's template. That happens when the skill was updated and the workspace's agents weren't, and the run would then follow this playbook with agents written for an older one. Tell the user which roles differ and ask once whether to update them.

- On a yes, run `scripts/agents.py update`. It rewrites each agent above its Profile section, keeps the section, backs up the old files, and prints the profile fields each template now asks for. Add any field an agent's Profile section or the profile lacks, as setup would, and tell the user. A session may spawn only the agents it registered when it started, so a new run stops here and asks the user to start `/deliver` again in a new session. An open batch carries on in this session with whichever agents it gets.
- On a no, go on, and say in the output at the end that the agents were out of date.
- A missing agent, or one with no Profile section, needs `/deliver setup`. Stop and say so.

An open batch belongs to the session that started it, and `show` prints that owner. If the owner is another session, or none is recorded, that session may still be running the batch, for example watching a deploy. Ask the user once whether it has stopped. Only on a yes, run `scripts/state.py batch claim` and resume. Otherwise leave the batch alone; `state.py` refuses this session's writes to it anyway.

Resuming:

- A ticket whose latest workflow `scripts/workflow.py agents` shows as running in this session, with a transcript write within the profile's silence threshold, is left alone.
- A ticket in `building` whose latest workflow is done: save its report with `scripts/save-report.py --run <run id> --label <ticket id> --out .deliver/<slug>/reports/<ticket id>.md`, read it, and go on from step 4.2.
- A ticket in `building` whose agent is gone (failed, killed, silent past the threshold, or in a workflow of another session, which ended with that session) is handled as Liveness says, from the ticket and its worktree as it stands.
- A batch in `final-review` whose review workflow has ended: save the findings of each axis whose agent is done (5.2), launch one continuation for an axis that isn't, and go on from 5.3 once both are saved. A confirm pass in `fixing` resumes the same way.
- A batch in `final-review`, `fixing`, `delivering` or `closing` otherwise continues from that step.

A new batch starts only when no batch is open. To start one while an older one is open, claim the older one as above, finish it from where it stands through its close (step 7.6), then start at step 1.

## 1. Budget

Read plan usage: in the desktop app, the session-management `get_usage` tool; elsewhere there is no reading, and the budget is a ticket count. Tell the user, in one message:

- the tickets and how they will batch (step 2),
- the weekly percentage used now,
- the estimate: tickets times the average weekly percentage per ticket recorded in `.deliver/costs.md`, or "no history yet" on the first batch. Weekly percentages measure one account's plan, and every session on it over the same days, so the estimate assumes the user's other work goes on at the rate it did. On a different account or plan from the rows there (the user says so, or a Slug cell names another plan), estimate in weighted tokens per ticket instead, and at step 7 name the plan in this batch's Slug cell, for example `ate-488-b4 (Team)`. A Slug cell that names roles (`cost.py` adds them) ran those roles off their defaults: average the rows that ran this run's settings, or say that none did,
- a proposed cap: the weekly reading at which no new ticket starts, written next to the current one ("now 91%, cap 97%"),
- what each role runs on: the output of `scripts/workflow.py settings`, with the command line's `--model` and `--effort` changes marked as this run's. The user can change any of them in the same answer.

This is the one question every run asks. The cap stops new tickets only. Once tickets are merged into the batch branch, the final review, the fix round and delivery run to the end, because stopping there leaves reviewed code undelivered; propose a cap that leaves room for them. When the answer can't be a reading (at or below the current one, or past 100), record your proposed cap and say so. Keep the readings, any consent the profile asks for in the answer (for example `mergeConsent=yes`) and this run's model and effort changes for step 3, which records them once `init` has made the new batch; `state.json` still holds the previous batch until then. Pick the first batch's slug now, and write the answer, and any other standing instruction the user gives for this run, to `.deliver/<slug>/notes.md` in the user's words, for a resumed or compacted session. Add one line there each time a step completes. Point at profile lines by name and never copy them: the profile can change during a run, and a copy goes stale. After every ticket, read usage again and record `weeklyAtEnd` on the ticket. At or above the cap, let the running tickets finish, start no new one, and take the tickets merged so far through steps 5 to 7. The rest stay queued for a later run. The batch's own end reading is taken once, at green CI (step 7.2).

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
- an estimated size of about 400 changed production lines or less. Tests and generated files don't count: a ticket that needs a large test suite is not oversized for it. An estimate built from per-file counts of existing code runs low, because it misses reuse refactors and the production code that grows with the tests: trial 2's tickets came in at 1.0 to 1.6 times such counts. Multiply such a count by 1.4.

Fix what you can in the tracker yourself: add missing risk tags, split a two-repository ticket into one per repository with a blocking edge (backend first), split an oversized ticket into slices with blocking edges, add the ADR link, and comment on each ticket what you changed. Stop and ask only when a fix needs a decision the ADR does not make.

An **added ticket** (one a batch filed at step 5.3 or 6) goes through the same bar; the agent that found the work drafted it to meet it. Its description starts with an `Added from` line, which marks code that doesn't widen scope (ADR 0004). An added refactor that a queued ticket builds on blocks that ticket: add the blocking edge in the tracker, so the refactor lands first.

Group the ready tickets into batches in blocking order. A batch closes at 6 tickets or about 2,500 production lines across its repositories, whichever comes first, so the final review can read all of it. Only the first batch is started; the next one starts after the first is delivered.

Write `.deliver/<slug>/tickets.md`: for each ticket in the batch, the id, title, repository, risk tags, estimated production lines, acceptance criteria and out-of-scope lines, copied from the tracker, and an added ticket's `Added from` line. End it with `## Queued`: one line per ticket waiting for a later batch, with its id, title, repository and areas. Agents read this file, not the tracker. Its tickets, queued ones included, are what the scope test counts.

Start `.deliver/<slug>/carry.md`, the carry list. It holds what the batch has to act on that no diff shows: items that a handoff, the grilling or an earlier batch left for this work, and facts an earlier measurement proved. One numbered line per item, ending in where it goes: a ticket in this batch (copy the item into that ticket's section of `tickets.md` too), or `outside` for the final review to rule on. Items are added as tickets finish (step 4.2) and closed at step 5.3.

## 3. Start the batch

For each repository in the batch:

```
git -C <repo> fetch origin <into>
git -C <repo> branch <batch-branch> origin/<into>
git -C <repo> push -u origin <batch-branch>
git -C <repo> worktree add <scratch-worktree> <batch-branch>
```

The scratch worktree is the orchestrator's own; ticket merges and checks happen there. Run the profile's setup rung for that repository in it (for example `npm ci`), so the first merge's checks can run. Then:

```
scripts/state.py init --slug <slug> --adr <adr-path>
scripts/state.py batch set weeklyAtStart=<n> weeklyCap=<n> [mergeConsent=yes] ['agentSettings={"<role>": {"model": "<model>", "effort": "<effort>"}}'] 'clerks=["<intake clerk run id>"]'
scripts/workflow.py settings --slug <slug>
scripts/state.py repo <name> set path=<repo> into=<into> batchBranch=<batch-branch> baseHead=<sha> scratch=<scratch-worktree>
scripts/state.py ticket <id> set repo=<name> phase=queued blockedBy=[...] estimate=<production lines>
scripts/state.py batch set phase=building
```

`agentSettings` holds only what this run changes, and only the fields it changes. `settings` exits on a role, model or effort no agent can run on; correct the value with the user before going on. `.deliver/` sits at the workspace root the profile names and is never committed. `init` records this session as the batch's owner and stores the ADR path as an absolute path; `cost.py` finds this session's transcripts from the run and agent ids in state, so `init` needs no session id. `init` moves a delivered batch's state file, or one written by deliver-v1, into `.deliver/archive/`, and refuses while a batch is open.

## 4. Per ticket

Start a ticket when everything it is blocked by is merged into the batch branch. Run at most two at once, and a second one only when neither blocks the other and they touch different repositories or clearly separate areas.

1. **Spawn the implementer** (`deliver-implementer`, in the ticket's workflow). The brief carries only:
   - the ticket id, and its section of `tickets.md` as the path and line range;
   - the ADR path and the carry list's path;
   - the repository, the ticket branch name from the profile's pattern, and the batch branch and its current head to branch from;
   - the worktree path and ports from the profile's sandbox conventions;
   - a database, assigned outright, when the ticket is tagged concurrency or migration or adds or edits a database-backed test (the profile says which tests those are). Never write "if you need one";
   - the ticket building alongside it, if any, and the areas that one touches;
   - its inbox path.

   Record `ticket <id> set 'runs=["<run id>"]' phase=building branch=<b> worktree=<w>`, write each continuation's run id at the end of `runs`, and queue the ticket's move to the tracker's in-progress state.
2. **On DONE**, check the report's risk checks: an answer for each of the ticket's risk tags, and for inputs, existing paths and reuse. Check its `In passing:` list too: each fix names the test that pins it, and a fix in a risk area has that tag's test and answer. When anything is missing, launch one continuation for all of it. In-passing work well past 200 production lines goes in your next message to the user; the final review reads it either way. Record `ticket <id> set inPassing=<production lines>`. Then route each item the implementer found and didn't fix, by how its line ends:
   - a later ticket in this batch: onto the carry list with that target, into that ticket's section of `tickets.md`, and into its brief;
   - `alongside`: into that implementer's inbox, and onto the carry list. The other ticket now builds on something no reviewer has seen, so the final review rules on it. A Decision that matters to the ticket alongside goes the same way;
   - `added`: save the drafts with `scripts/save-report.py --run <run id> --label <ticket id> --section "## Added tickets" --out .deliver/<slug>/added/<ticket id>.md`, and put each draft's title on the carry list as `added`;
   - `outside` or `needs you`: onto the carry list as it stands, for the final review to rule on.

   Check every report against its own inbox: a note the report doesn't answer arrived after the implementer's last read, and gets a continuation with that note as its one thing, before step 4.3.
3. **Merge into the batch branch**: `scripts/merge-ticket.sh --scratch <scratch-worktree> --ticket-branch <b> --ticket <id> --title "<title>" --estimate <n> --check "<profile unit command>" ...`. Add a `--check` for the repository's typecheck when its unit rung doesn't compile the code (a Jest-only rung doesn't): two tickets built side by side can each pass their tests and still break each other's types. It merges with a merge commit, runs `verify-head.sh`, runs the checks only when the batch head moved since the ticket branched, pushes the batch branch, and prints the ticket's actual size. Exit 10 means a conflict: a continuation merges the batch head into the ticket branch and resolves it; then run the script again. Exit 11 means a check failed on the merged head: launch a continuation with the failing command's tail.
4. **After the merge**: `scripts/sweep.py --path <repo> --ticket <b> --merged-into <batch-branch>` removes the worktree and the local ticket branch. Hand the clerk the ticket's move to the tracker's in-review state with a comment (its Decisions and its risk checks, from the commit message), and the queued writes. Record `phase=merged head=<sha> prodLines=<n>` and the usage reading (step 1).

   From here the batch bound (step 2) counts actual lines: the merged tickets' `prodLines` plus the estimates of those not yet started. When that passes the bound, the tickets not yet started wait for the next batch. Say so in your next message to the user; it is not a stop.

**BLOCKED from an implementer.** If the ADR, `tickets.md` or the grilling in this session answers it, launch a continuation with the answer in its brief, and queue the answer as a comment on the ticket. If not, it is a stop (step 8).

**Liveness.** A workflow notifies you when it returns, with `null` for an agent that ended without a report. Then, or past the profile's silence threshold, run `scripts/workflow.py agents <run id>`:

- Running, with no transcript write within the threshold: the agent hung, or its session stopped or restarted (a restarted session keeps its id, and its old workflows never end). Stop the workflow with TaskStop and the task id from its launch, if this session still has it, and treat the agent as failed. A continuation never shares a worktree with a live agent.
- Failed on the usage limit (its error names a 429, a usage limit or a session limit, or `get_usage` shows the 5-hour window at its limit): an agent doesn't wait for the reset as this session does. Launch its continuation once the limit has reset; that continuation doesn't count.
- Failed because its agent type wasn't found: the role agent isn't registered in this session. Launch nothing. It is a stop (step 8): the user starts `/deliver` in a new session, which resumes from state.
- Killed, when you didn't stop it: the user stopped it from the background tasks. Ask what they want before launching anything.
- Any other failure: one continuation to finish the work. For a ticket, record `ticket <id> set continuations=<n>`, so a resumed session knows it is spent. A second failure is a stop.

This holds for a reviewer or fixer too.

**Reports that come back.** The harness can deliver a finished agent's report a second time, hours later, as a hand-back message or a task notification. When that report's step has already moved on, note it in one line and make no tool call.

## 5. Final review

When every ticket in the batch is merged:

1. In each scratch worktree: `git fetch origin <into> && git merge --no-ff origin/<into>`. On a conflict, `git merge --abort` and give it to a fixer (step 6, as `merge fix`) before anything else, and record its run id as `batch set 'fixer=["<run id>"]'`. Run the profile's full test rung once per repository, one repository after the other: two full rungs at once starve each other, and a test worker can crash. Where the profile names database-backed tests, the rung includes them: create the batch database with the profile's test-database command at this head, and set the profile's switch for the run. Tests the rung skips count as not run, and the batch PR says so. Record `batch set phase=final-review` and each repository's `reviewedHead`.
2. Spawn the correctness reviewer and the quality reviewer in one workflow (`deliver-correctness-reviewer`, `deliver-quality-reviewer`). Each gets: `tickets.md`, the ADR path, the carry list, and per repository the path, `baseHead` and `reviewedHead`. The correctness reviewer also gets its worktree path, port and database from the profile's sandbox conventions. Record its run id as `batch set 'reviewers=["<run id>"]'`. Each returns its findings as its final message. Save each with `scripts/save-report.py --run <run id> --label correctness --heading "# Correctness findings" --out .deliver/<slug>/findings-correctness.md`, and with `--label quality` and `"# Quality findings"` to `findings-quality.md`; never retype a report. After a continuation, save that axis from the continuation's run. The fixer reads those files.
3. **Sort what the batch found** into findings, added tickets and follow-ups. Close the carry list: end each item's line with the reviewers' ruling. Rule yourself on an item no reviewer ruled on, with the scope test (ADR 0004): small and in scope, a finding for the fixer's brief; in scope and more than about 200 lines, an added ticket, from the implementer's saved draft or one you write from the item; out of scope, a follow-up. When you can't tell, it is a follow-up. An item for a ticket queued for a later batch goes into `notes.md`, for that batch's carry list. Save each reviewer's drafts with `scripts/save-report.py --run <run id> --label <axis> --section "## Added tickets" --out .deliver/<slug>/added/<axis>.md`; exit 1 means that axis wrote none.

   Then hand the clerk one list:
   - each added ticket, as a new ticket in the tracker's ready state, linked to the ADR, with the risk labels its draft names. Its title is the draft's heading. Its description is the line `Added from <ticket id or axis>` and then the draft, which the clerk copies from the `### <title>` section of its file;
   - each follow-up (the reviewers' Follow-up sections, and the carry list's), as a new ticket in the backlog, linked to the ADR and marked `dedupe:` with its file and the defect's key words. One marked `needs you` is assigned to the user.

   Record `batch set followUps=[...] addedTickets=[...] needsYou=[...]` from the clerk's lines (`needsYou` repeats the follow-ups assigned to the user; a `commented` line records the issue it commented on), and end each carry-list line with its ticket's id. Add the added tickets to `notes.md` as queued for the next batch. No item stays open past this step.
4. With no Blocking, Should-fix or Nit finding, and no carry item ruled a finding, go to step 7.

## 6. The fix round

Spawn one fixer (`deliver-fixer`) with both findings files, the carry items ruled a finding at 5.3, the ADR path, `tickets.md`, and per repository the path, the batch head, and a fix branch and worktree of its own from the profile's patterns. Git will not check out the batch branch in a second worktree while your scratch worktree holds it, so the fixer works on its fix branch and never pushes. It fixes every Blocking, Should-fix and Nit finding, in the batch's code or outside it, up to about 200 production lines each, runs the tests the profile names, commits, and reports per finding: fixed (with sha), disputed (with the reason) or too big (with a draft). Its report also gives the production lines it changed outside the batch's code, and the risk areas they touch. Write its run id at the end of `fixer`, after a merge fix's from 5.1, and so for every later fixer, rewriting the whole list each time. A fixer that reports BLOCKED (a fix would change an ADR decision) is a stop (step 8). With the user's answer, launch a continuation fixer on the same fix branch and worktree with that decision; it is still the one round.

Then, yourself:

- In each scratch worktree, `git merge --ff-only <fix branch>` and push the batch branch; `scripts/sweep.py --path <repo> --ticket <fix branch> --merged-into <batch-branch>` removes the fixer's worktree and branch.
- `scripts/verify-merge.py --repo <path> --delta <reviewedHead> <new head>`: list the delta and read every hunk against the finding that asked for it, a hunk outside the batch's code as closely as one in it.
- Each line under the fixer's `Decisions replaced:` goes into the batch PR's description (7.1) and that ticket's done comment (7.6); until then the ticket's tracker comment describes the old design.
- A disputed finding: decide it from the findings file and the fixer's reason. If deciding it would change the ADR, it is a stop.
- A finding reported too big: save the fixer's drafts with `scripts/save-report.py --run <run id> --label fixer --section "## Added tickets" --out .deliver/<slug>/added/fixer.md`.
- Spawn a confirm pass, in one workflow, on the delta only (`--confirm` in each brief, with the earlier findings file): one confirm reviewer per axis that raised a Blocking finding, and the correctness reviewer when the fixer's work outside the batch's code passes about 150 production lines or touches a risk area. Record the run id with `batch set 'confirm=["<run id>"]'`, and save each axis's findings with `save-report.py --run <run id> --label confirm-<axis>` to `findings-<axis>-confirm.md`. Otherwise no reviewer sees the delta.
- A confirm pass's Should-fix and Nit findings go to a continuation fixer on the same fix branch and worktree, with that findings file; it is still the one round, and no confirm pass follows it. Merge and read its delta as above. A Blocking finding from the confirm pass, an earlier one still open or a new one, is a stop (step 8).
- When the fixers reported anything too big, or a confirm pass wrote Follow-ups or Added tickets, hand the clerk one list that files them as 5.3 does, wait for its report, and add the ids to `followUps`, `addedTickets` and `needsYou`.
- Run the profile's unit rung in the scratch worktree, and the database-backed tests again when step 5.1 ran them. Record the new `reviewedHead`, and `batch set phase=delivering`.

The fixer is also who you spawn for a conflict in step 5.1, a failing CI run on the batch PR, and a deploy that fails for a code reason. Each of those gets one attempt.

## 7. Deliver

Per repository, in the profile's order (backend before frontend):

1. Open the batch PR from the batch branch into the integration branch with the profile's command. Description: what each ticket did, its Decisions and its `In passing:` lines, with any Decision the fix round replaced marked as replaced, the final review's summary (findings fixed, disputed, too big), the added tickets and follow-ups the batch filed, with those that need the user marked, which database-backed tests ran, and the tickets it closes. When the Decisions don't fit the profile's description limit, link each ticket's tracker comment from step 4.4 instead. With a squash strategy the description becomes the commit message on the integration branch and the ticket commits leave its history, so the description must stand on its own. Record `repo <name> set pr=<id>`.
2. Wait for CI and the required policy builds with a background shell loop on the profile's PR status command, never by polling in turns. A failure gets one fixer attempt, then it is a stop. When the last repository's CI is green, read usage and `batch set weeklyAtEnd=<n>`. The batch's own work ends there; the waits after it are the user's, so nothing later overwrites the reading.
3. Vote as the profile allows (the creator's vote, when the policy counts it) and complete the PR with the profile's batch strategy, merge commit or squash. When the profile says batch PRs are completed by hand, don't try the vote: go straight to the stop message below. Claude Code's permission check may refuse your own vote or completion as self-approval, whatever consent the state records. Don't look for another way to approve: stop (step 8). The stop message starts with the profile's by-hand completion (the fields to set in the host's completion dialog), then gives the PR link. Continue at 7.4 when the user says it is merged.
4. `scripts/verify-merge.py --repo <path> --reviewed <reviewedHead> --merged <integration head>`: the merged tree must equal the reviewed tree, or be the clean merge of it onto a target that moved.
5. Deploy per the profile: watch the automatic deploy by commit, or queue it with the profile's commands and watch each run by id; then run the profile's after-deploy steps. A failure: read the run's log tail once; a code cause gets one fixer attempt and a new batch PR from the fix; a second failure is a stop.
6. **The close**, once per batch, after the last repository's deploy: `scripts/state.py batch claim --from delivering --to closing`. If the claim fails, another session is closing this batch: stop and tell the user. Otherwise:
   - per repository, `scripts/sweep.py --path <repo>` with the profile's sweep arguments and `--ticket <batch-branch>` removes the scratch worktree and the batch branch, local and remote. `git -C <repo> worktree list` shows any reviewer worktree left behind (the profile's pattern); `scripts/sweep.py --path <repo> --worktree <path>` removes it;
   - drop the batch database and every ticket, fixer and reviewer database this batch's briefs assigned;
   - move every ticket to the tracker's done state with a comment: the merge commit, the deploy run, and any Decision the fix round replaced;
   - `batch set phase=delivered`, run `scripts/cost.py --batch <slug> --summary-row` and append its row to `.deliver/costs.md`. When the file's header row differs from what `scripts/cost.py --summary-header` prints, replace its header and separator rows with that first. Older rows keep their cells, and a column they lack shows blank.

When the batch filed added tickets, take them through intake (step 2) before the next batch starts. Each joins the next batch in blocking order, or a later one when the bound is full. If a batch is waiting, go to step 3 with it; the budget and the model and effort changes from step 1 still hold, so record the same `agentSettings` on it.

In tracker text and PR descriptions, write slugs and branch names in backticks: the tracker may turn a bare `ate-488-b2` into a link to ATE-488.

## 8. Stops

Stop and ask the user only for:

- a product or scope decision that the ADR, `tickets.md` and the grilling do not answer;
- anything past the integration branch, anything touching secrets, or a write to a shared database (the user runs guarded scripts);
- a finding or dispute whose resolution would change the ADR;
- a CI run or deploy that fails again after its one fix attempt;
- an agent that fails again after its continuation, or whose role agent this session hasn't registered (Liveness);
- a fixer's BLOCKED, or a Blocking finding from a confirm pass (step 6);
- a vote or PR completion the permission check refuses (step 7.3);
- role agents that are missing or differ from the installed skill's templates (step 0);
- a batch another session owns (step 0) or is closing (step 7.6);
- the weekly cap from step 1.

Everything else you decide, record in the tracker or the PR description, and continue. When you stop, say what is decided, what the options are, and your recommendation, in one message.

## Output at the end

Start with **Needs you**: each follow-up assigned to the user, one line each with its id and what it needs, or `none`. Then a table per batch: ticket, repository, production lines against the estimate, in-passing lines, merged head. Then the batch PRs and deploy runs; the added tickets filed, and the batch each joins; the follow-ups filed; the quality reviewer's Refactors left; the cost row; the correctness reviewer's peak context (`scripts/cost.py --batch <slug> --markdown` prints it) and the findings per 1,000 lines (Blocking and Should-fix over the batch's production lines), which show whether the batch bound still holds (ADR 0004); the weekly percentage used. For a change a user can see, add a short smoke test on the environment it deployed to: where to click and what should happen. The batch's checks are tests, and no agent used the change against a running backend.

## State keys

`status` and `cost.py` read these keys. `scripts/state.py` refuses a phase not listed here and a key that looks like a misspelling of a listed one, and warns on any other new key:

| Scope | Keys |
|---|---|
| batch | `slug`, `adr`, `phase` (`building`, `final-review`, `fixing`, `delivering`, `closing`, `delivered`, `paused`), `owner` (the session id; set by `init` and `batch claim`), `startedAt`, `closedAt`, `sessionDir`, `sessionJsonl`, `weeklyAtStart`, `weeklyCap`, `weeklyAtEnd` (at green CI), `mergeConsent` (`yes` when the profile makes a vote depend on it), `agentSettings` (`{role: {model, effort}}`, this run's changes only), `reviewers`, `fixer`, `confirm`, `clerks` (lists of workflow run ids; batches before workflows hold agent ids, and `reviewers` as `{"correctness": id, "quality": id}`), `followUps`, `addedTickets`, `needsYou` (lists of tracker ids; `needsYou` repeats the follow-ups assigned to the user) |
| repo | `path`, `into`, `batchBranch`, `baseHead`, `scratch`, `reviewedHead`, `pr`, `mergedHead`, `deployRuns` (list) |
| ticket | `repo`, `phase` (`queued`, `building`, `merged`, `blocked`), `blockedBy` (list), `estimate`, `branch`, `worktree`, `runs` (workflow run ids, the latest last), `agent` (the agent id, in batches before workflows), `head`, `prodLines`, `weeklyAtEnd`, `continuations` (the number launched for an agent that failed or went silent; a usage-limit one doesn't count), `inPassing` (production lines the implementer fixed in passing) |

Record every run id the moment the launch returns it. `cost.py` counts every agent of a recorded workflow on that key's row; an agent whose run id is missing from state lands in its unassigned rows. State files from batches before the ticket reviewer was dropped also hold `reviewer` and `flags` on tickets; `cost.py` still reads `reviewer`.
