# skills

Reusable Claude Code skills. Install with the skills.sh CLI:

```bash
npx skills add josteinhanssen/skills
```

Skills live under `skills/<category>/<name>/SKILL.md`, the layout the installer expects, and are linked into `~/.claude/skills/`. The words the skills use are defined in [CONTEXT.md](CONTEXT.md); decisions about their design are in [docs/adr/](docs/adr/).

| Skill | Purpose |
|---|---|
| `engineering/deliver` | Take the ADR and tickets from a grilling session to the integration branch and its dev deploy with sub-agents: Opus builds, Haiku flags, one strong review per batch |

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

So the grilling is the plan. The decisions a spec used to make, the implementer now makes and records; review moves from per PR to per batch; and every agent's context stays small. ADR [0001](docs/adr/0001-deliver-builds-from-tickets.md) records the trade: the pre-code gate did find real defects (a measured deadlock, a token-policy hole), and those now have to come from risk-tag tests or the final review.

### The flow

1. **Budget.** The orchestrator reads plan usage, proposes a weekly cap, and the user agrees once.
2. **Intake.** Every ticket gets checked against the bar (behavioural acceptance criteria, blocking edges, one repository, risk tags, out of scope, an ADR link, about 400 lines) and fixed in the tracker. Tickets group into batches of up to 6 tickets or about 2,500 lines.
3. **Per ticket.** A fresh implementer builds from the batch head and commits with a `Decisions:` list. A ticket reviewer writes up to 15 flags. The implementer fixes the flags it can confirm and answers the rest. `merge-ticket.sh` merges the ticket into the batch branch.
4. **Final review.** The integration branch is merged in and the full tests run. A correctness reviewer and a quality reviewer read the whole batch in parallel and rule on every flag. Follow-ups outside the batch's own code become tickets.
5. **Fix round.** One fixer, one round. The orchestrator reads the delta, and a confirm pass runs only after a Blocking finding.
6. **Deliver.** One batch PR per repository with a merge commit, CI, the vote, a check that the merged tree is the reviewed tree, the deploy watched to success, tickets done, and a cost row.

The session stops for the user only for a product or scope question, anything past the integration branch or touching secrets or shared databases, a finding that would change the ADR, a CI run or deploy that fails after its one fix attempt, and the weekly cap.

### Roles

| Role | Model | Scope | Tools |
|---|---|---|---|
| Orchestrator | the user's session | the whole run | everything, including the tracker |
| Implementer | Opus 5.5, high | one ticket, resumed once for flags | files, shell, skills |
| Ticket reviewer | Haiku 4.5 | one ticket's diff, one pass | read, shell, write its flag file |
| Correctness reviewer | Opus 5.5, high | the whole batch | read, shell, write its findings |
| Quality reviewer | Opus 5.5, high | the whole batch, against its own fixed bar | read, shell, write its findings |
| Fixer | Opus 5.5, high | the one fix round, or one CI or deploy failure | files, shell, skills |

No role gets MCP servers, and none spawns another agent. The quality reviewer's bar covers reuse, size, module depth, named smells and error handling that hides failures. It applies whether or not a repository documents standards, and "the existing code does it this way" is never a defence.

### Cost controls

- `autoCompactWindow: 300000` in the user settings caps every session and agent at 300k tokens of context.
- Agents are fresh per ticket or per batch and report in under 300 words; the orchestrator never reads a transcript.
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
  templates/               the profile and the five role agents
  scripts/                 state file, ticket merge, merge verification, sweep, cost, quiet runner
```
