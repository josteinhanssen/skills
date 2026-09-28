# skills

Reusable Claude Code skills. Install with the skills.sh CLI:

```bash
npx skills add josteinhanssen/skills
```

Skills live under `skills/<category>/<name>/SKILL.md`, the layout the installer expects, and are linked into `~/.claude/skills/`. The words the skills use are defined in [CONTEXT.md](CONTEXT.md); decisions about their design are in [docs/adr/](docs/adr/).

| Skill | Purpose |
|---|---|
| `engineering/deliver` | Take the ADR and tickets from a grilling session to the integration branch and its dev deploy with sub-agents: Opus builds and checks its own risks, one strong review per batch |

## deliver: design

The session that ran the grilling and wrote the ADR and the tickets runs `/deliver <ADR or tickets>`. From then on it only stops when it needs the user. It checks each ticket against a bar and fixes the tickets in the tracker. It builds them one or two at a time onto a batch branch, reviews the batch once in depth, merges it into the integration branch, and watches the deploy.

### Why it looks like this

The previous version (tag `deliver-v1`) planned a batch, then wrote a spec per PR that settled every judgment before a small-model implementer typed it. On the ATE-488 batch (2026-09-24/25) that merged nine PRs with no defects found after merge, but it cost about 33M weighted tokens per merged PR and ran into the user's 5-hour and weekly limits. Sub-agent cost by role:

| Role | Agents | Weighted | Share of sub-agents |
|---|---|---|---|
| Spec planner | 14 | 284.8M | 70% |
| Implementer | 10 | 50.7M | 12% |
| Gate review and confirm passes | 17 | 27.0M | 7% |
| Batch planner and plan review | 2 | 16.2M | 4% |
| PR review, both axes | 31 | 16.5M | 4% |
| Other (grilling exploration, UI critique) | 11 | 13.2M | 3% |

The spec planners wrote each change in full, pinned it by hash, measured mutation probes and replayed it, and then the implementer did the same work again. PR review, the part that most looked like a cost worth cutting, was 4%. What made everything expensive was context size times calls. Planners carried 534k tokens of context on every call, and the orchestrator 509k across 526 calls. Weighted tokens here are input 1×, cache read 0.1×, cache write 2×, output 5×.

So the grilling is the plan. The decisions a spec used to make, the implementer now makes and records; review moves from per PR to per batch; and every agent's context stays small. ADR [0001](docs/adr/0001-deliver-builds-from-tickets.md) records the trade: the pre-code gate did find real defects (a measured deadlock, a token-policy hole), and those now have to come from risk-tag tests or the final review. ADR [0002](docs/adr/0002-implementers-check-their-own-risks.md) replaced the per-ticket Haiku reviewer with risk checks the implementer answers itself.

### The flow

1. **Budget.** The orchestrator reads plan usage, proposes a weekly cap, and the user agrees once.
2. **Intake.** Every ticket gets checked against the bar (behavioural acceptance criteria, blocking edges, one repository, risk tags, out of scope, an ADR link, about 400 production lines) and fixed in the tracker. Tickets group into batches of up to 6 tickets or about 2,500 production lines. A carry list starts with what the batch must act on that no diff will show.
3. **Per ticket.** A fresh implementer builds from the batch head, answers the risk checks for its tags plus inputs, existing paths and reuse, and commits with `Decisions:` and `Risk checks:`. `merge-ticket.sh` merges the ticket into the batch branch and prints its actual size. Its out-of-scope notes go on the carry list.
4. **Final review.** The integration branch is merged in and the full tests run, database-backed ones included. A correctness reviewer and a quality reviewer read the whole batch in parallel, starting from the risk checks and the carry list. Follow-ups outside the batch's own code become tickets, and every carry item is resolved, filed or dropped.
5. **Fix round.** One fixer, one round. The orchestrator reads the delta, and a confirm pass runs only after a Blocking finding.
6. **Deliver.** One batch PR per repository with the profile's strategy (merge commit or squash), CI, the vote, a check that the merged tree is the reviewed tree, the deploy watched to success, and a close that runs once: tickets done, worktrees and databases removed, and a cost row.

The session stops for the user only for a product or scope question, anything past the integration branch or touching secrets or shared databases, a finding that would change the ADR, a CI run or deploy that fails after its one fix attempt, and the weekly cap.

### Roles

| Role | Model | Scope | Tools |
|---|---|---|---|
| Orchestrator | the user's session | the whole run | everything, including the tracker |
| Implementer | Opus 5.5, high | one ticket and its risk checks | files, shell, skills |
| Correctness reviewer | Opus 5.5, xhigh | the whole batch | read, shell, write in its own scratch worktree; returns its findings |
| Quality reviewer | Opus 5.5, xhigh | the whole batch, against its own fixed bar | read, shell; returns its findings |
| Fixer | Opus 5.5, high | the one fix round, or one CI or deploy failure | files, shell, skills |

No role gets MCP servers, and none spawns another agent. The quality reviewer's bar covers reuse, size, module depth, named smells and error handling that hides failures. It applies whether or not a repository documents standards, and "the existing code does it this way" is never a defence.

### Cost controls

- `autoCompactWindow: 300000` in the user settings caps every session and agent at 300k tokens of context.
- Agents are fresh per ticket or per batch and report in under 300 words, except the final reviewers, whose report is their findings (under 900); the orchestrator never reads a transcript, and `save-report.py` copies the findings from the reviewers' transcripts so the orchestrator doesn't retype them.
- An explicit `tools` list per agent keeps MCP tool definitions out of every call.
- One or two tickets at a time, each from the batch head: no rebases, grants or locks.
- `autoContinueAtUsageLimit: true` lets a batch wait out a 5-hour limit; the weekly cap stops it.
- `scripts/cost.py` appends one row per batch to `.deliver/costs.md`: weighted tokens per ticket, an Opus-equivalent figure that prices Haiku and Sonnet turns at their share of Opus, and the weekly percentage per ticket. The target is 12M weighted per ticket or less over the first three batches.

### Commands

| Command | What it does |
|---|---|
| `/deliver <ADR \| tickets> [--into <branch>]` | the whole run, resumable from `.deliver/state.json` |
| `/deliver status` | prints the batch from the state file, no model work |
| `/deliver setup` | writes or migrates the project profile, installs the role agents, checks the two settings |

### Trials

**1. `ate-488-b1` (Memerix backend, 2026-09-25).** Three small tickets (ATE-514, ATE-516 and ATE-500's backend half, about 110–150 production lines each) went through one batch PR to dev: 6.01M weighted tokens, 2.00M per ticket. The target is 12M; the old flow's last full batch cost 41.6M per ticket. Weekly usage went from 85% to 86%.

| Role | Agents | Weighted | Opus-eq | Share (opus-eq) |
|---|---|---|---|---|
| Implementer | 3 | 1.74M | 1.74M | 32% |
| Ticket reviewer (Haiku) | 3 | 0.76M | 0.19M | 3% |
| Final review, both axes | 2 | 0.92M | 0.92M | 17% |
| Fixer | 1 | 0.78M | 0.78M | 14% |
| Orchestrator | — | 1.82M | 1.82M | 33% |

What it taught the skill:

- The harness refuses a Write of a report-like file from a sub-agent ("Subagents should return findings as text"). It stopped both final reviewers' `findings-*.md` and let the ticket reviewers' `flags/*.md` through. Final reviewers now return their findings as their report, and the orchestrator saves them.
- The Haiku ticket reviewers flagged nothing on all three tickets, while the quality reviewer found four Should-fix issues. One of them, a duplicated test helper, was within the Haiku reviewer's checks. Its checks now also cover test helpers, a rule written in several places, and the profile's naming and API rules. The next batch decides whether it stays.
- The orchestrator made 80 calls, and its context grew from 79k to 253k tokens. Most of the growth was its own reasoning and tool inputs; the tracker's echoes of whole tickets were about 19k.
- Claude Code's permission check refuses the orchestrator's own vote on the batch PR as self-approval, whatever consent the state records. That is now a designed stop, with the by-hand completion named in the profile.
- The weekly cap now stops new tickets only, so merged tickets always reach delivery. Plan usage reads in whole percents, so the cost row takes the weekly delta per batch.
- The final reviewers moved from high to xhigh effort. They are the last check before dev and 17% of the cost; the implementers stay at high until a batch shows a need.
- Smaller fixes: the intake size bar counts production lines only, `verify-merge.py` recognises .NET `*.Tests` projects, `sweep.py` accepts a branch the host already deleted, and `cost.py` finds the session from the agent ids.

**2. `ate-488-b2` (Memerix backend, 2026-09-25 to 2026-09-28).** ATE-494's partner-order intake, split into six tickets (ATE-521 to ATE-526), went through one batch PR (PR 5919) to dev: 21.88M weighted tokens, 3.65M per ticket, 3.43M Opus-equivalent. Weekly usage per ticket is an estimate, about 0.6%: the end reading was taken after a weekend of other use. ATE-526's implementer alone used 4.19M on a 1,350-line diff.

| Role | Agents | Weighted | Opus-eq | Share (opus-eq) |
|---|---|---|---|---|
| Implementer | 6 | 10.74M | 10.74M | 52% |
| Ticket reviewer (Haiku) | 6 | 1.72M | 0.43M | 2% |
| Final review and confirm pass | 3 | 3.15M | 3.15M | 15% |
| Fixer | 1 | 2.06M | 2.06M | 10% |
| Orchestrator | — | 4.19M | 4.19M | 20% |

What it taught the skill:

- The Haiku ticket reviewer raised one flag in six tickets and twice wrote no flag file. The final review found four defects in diffs it had read, and a Blocking race whose other half was outside every diff. It is dropped (ADR 0002). Implementers answer risk checks, and the correctness reviewer checks the answers.
- Knowledge from outside the diff had nowhere to go: the handoff's follow-ups and the implementers' out-of-scope notes were carried by hand, and the final review named only part of them. The carry list holds them, and every item is ruled on before delivery.
- Two tickets built side by side collided in a shared test count. Implementers keep new tests to their own classes and rows, and each brief names the ticket building alongside.
- The SQL Server tests never ran: the full rung skipped 17 to 19 of them, and a brief said "only if you need SQL Server". The profile now names database-backed tests, a brief assigns a database outright for a concurrency or migration ticket, and the final full run uses a batch database.
- The batch PR was completed by hand as a squash again, which took the ticket commits and their Decisions off `main`. Memerix now squashes on purpose, and the PR description carries the Decisions or links to them.
- A second session resumed b2 while the first was still watching its deploy, and closed it. `state.py` now records the owning session and refuses writes from another until it claims the batch, and the close runs only once.
- Scripts: `sweep.py` run outside a repository exited 0 and now fails; `merge-ticket.sh` prints each ticket's actual size and flags overruns (b3's first tickets came in at 1.6 times their estimates); `sweep.py --worktree` removes a reviewer's worktree; `state.py show` prints the weekly readings by name. `cost.py` takes agent ids as a string, list or map.
- The orchestrator retyped about 900 words of findings three times, and spent turns on reports the harness re-sent hours later. `save-report.py` copies findings from the transcript, and a re-sent report gets one line. The tracker's echo of each ticket on every state change stayed, at about 2.5k tokens a move.
- The batch's end reading of weekly usage is now taken at green CI, before the user's merge and the deploy wait.

### History

`deliver-v1` (tag) is the plan, spec, run and close design with its seven trials, from the wave-N baseline through hygiene-2, and the lessons each one fed back into the skill. Read it with `git show deliver-v1:README.md`. The ATE-488 figures above are that design's last measurement.

### Repository layout

```
CONTEXT.md                 the words the skill uses
docs/adr/                  design decisions
skills/engineering/deliver/
  SKILL.md                 commands, words, principles
  agents/openai.yaml       interface shim for the installer
  reference/               run, status and setup playbooks
  templates/               the profile and the four role agents
  scripts/                 state file, ticket merge, merge verification, sweep, cost, report saver, quiet runner
```
