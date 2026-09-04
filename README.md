# skills

Reusable Claude Code skills. Install with the skills.sh CLI:

```bash
npx skills add josteinhanssen/skills
```

Skills live under `skills/<category>/<name>/SKILL.md`, the layout the installer expects, and are linked into `~/.claude/skills/`.

| Skill | Purpose |
|---|---|
| `engineering/deliver` | Plan, spec, implement, review, merge and close a batch of tickets with sub-agents, at the lowest token cost that keeps quality |

## deliver — design

`/deliver` turns a goal into merged, verified, cleaned-up work. It puts the expensive model where judgment happens (planning, plan review, PR review, rulings) and a cheaper model where the judgment has already been written down (implementation). It was distilled from a delivery wave that merged twelve tickets in a day with seven parallel agents; that wave's numbers are the baseline it is measured against.

### What it is built on

`deliver` extends the [mattpocock/skills](https://github.com/mattpocock/skills) set rather than replacing it. `to-spec` and `to-tickets` remain the planning front end (a spec, then tracer-bullet tickets with blocking edges); `grilling` runs the interview when the input is only a goal; `code-review`'s Standards-and-Spec split and its verbatim-report rule are the reviewer model; `tdd`, `diagnosing-bugs`, `resolving-merge-conflicts` and `codebase-design` are called where an implementer or planner needs them. What those skills lack, and `deliver` adds: a spec-depth gate, model and effort control per role, an orchestrator loop with file-backed state, exclusive-resource grants, post-merge hygiene, and cost accounting. Frontend work can opt into `impeccable` through the project profile.

### The cost model

Where a delivery wave's sub-agent tokens went before this skill existed (seven implementers and their reviewers, one day):

| Bucket | Share |
|---|---|
| Implementers on the large model | ~38% |
| Implementers on the small model plus one large-model sweep | ~16% |
| Substitute reviewers, two to five passes per PR | ~45% |

Review rounds cost as much as implementation, and the round count came from judgment calls the tickets left open (caps, what stays in the browser, fixture shape), not from the model. Tightly scoped tickets on the small model closed in one or two rounds at a fifth of the cost. So the levers are:

1. The small model implements, from a spec that contains no open judgment.
2. One large-model review pass per axis, with mechanical checks replacing the rest.
3. A hard cap on review rounds: two full passes, then a closing round, then merge.
4. The orchestrator's own context stays small: reports go to files, it reads bounded summaries.

Not used: larger PRs (they cost more review rounds) and skipping review for "mechanical" tickets (reviewers found a real coverage loss on nearly every PR of the baseline wave, small-model tickets included).

Recomputed with `scripts/cost.py` (per-turn usage, the billed basis), the same wave looks different: implementation is over 80% of weighted cost on every ticket and review 10 to 20%, because cost scales with turns times context size and a long implementation run drags a large context through hundreds of turns. A small-model ticket that ran 400 tool calls cost more than a large-model ticket that ran 150. So the first lever is the number of turns and the size of the context an implementer carries (a complete spec, targeted reads, quiet commands, fresh reviewers), the second is the model, and the third is the round cap.

The metric is tokens per merged ticket, split into plan, implement, review and orchestrate, reported raw and cost-weighted (cache reads about 0.1×, cache writes about 2×, output about 5×), with quality alongside as findings per PR and defects found after merge. `scripts/cost.py` computes it by summing every turn's usage block from the session transcripts, which is what is billed; those figures are much larger than the "sub-agent tokens" a completion notice shows, so a baseline is only comparable when it was computed with the same script. Target against the baseline: half the review bucket and most implementation on the small model, which is roughly a 50 to 60% cut if quality holds.

### Commands

One skill, six sub-commands, each runnable alone:

| Command | What it does | Model work |
|---|---|---|
| `setup` | Interviews for the project profile, installs the role templates into the project's `.claude/agents/` | one large-model turn |
| `plan` | A goal, a tracker issue or a spec file becomes a reviewed plan of tickets with blocking edges, file overlap and a model per ticket | planner + plan-reviewer |
| `spec` | One ticket becomes a spec file the small model can execute; gated by the plan-reviewer's checklist | planner + plan-reviewer |
| `run` | Orchestrates implementation of a batch to merge: spawns implementers, grants exclusive resources, routes reviews, merges, verifies | orchestrator + implementers + reviewers + judge |
| `close` | Authoritative verification on the merged head, cleanup of worktrees and branches, deploy per profile, tracker comments, cost table | orchestrator |
| `status` | Reads the state file and prints the batch, no model work beyond formatting | none |

`plan` accepts all three inputs and says which path it took; a bare goal first runs `grilling` and `to-spec`, then `to-tickets`.

### Roles and models

Installed as agent definitions with `model` and `effort` set, so the split is enforced rather than remembered.

| Role | Default | Spawned with |
|---|---|---|
| Planner | large, extra high | the goal or spec, the profile, the repo |
| Plan-reviewer | large, high | the plan or spec, the checklist; verdict only, never edits |
| Implementer | small, high | one spec file, the profile extract, the sandbox assignment |
| Escalation implementer | large, high | the same, when a ruling needs design judgment a spec cannot express |
| Standards reviewer / Spec reviewer | large, medium | repo path, PR id, base and head refs, changed files, the spec, totals; never the implementation transcript (`fork_turns: none`) |
| Ruling judge | large, extra high | the spec and one question, when an implementer reports BLOCKED; the answer is written into the spec so it is never asked twice |
| Orchestrator | large, high (small is a later experiment) | the profile, the state file |

Effort is spent where a wrong answer is expensive to discover later: the planner's unwritten judgment becomes a review round, the judge's ruling is rare and final. The orchestrator's work is procedural and runs for hundreds of turns, so its reasoning depth stays ordinary and its context stays small.

The implementer template absorbs the context-budget rules of `implement-efficiently`, which it supersedes.

### The spec file

One spec equals one PR equals one implementer run. A ticket that needs several PRs gets several specs. Specs are committed under the project's docs tree while live and deleted on merge; the ticket's completion comment links the spec's last commit. Sections:

- Goal and non-goals; Model (small or large) and Size (files, tests)
- Rulings: every judgment call, already decided
- Files to touch; files not to touch
- Tests by name, what each proves, and at which rung
- Fixtures and harnesses to reuse, with paths
- Acceptance checks as commands
- Mutation probes to run
- Bookkeeping edits (ledger row, budget file, docs)
- Out of scope, and where it is ticketed
- Reviewer focus: what the Spec reviewer verifies first

The gate: the plan-reviewer ticks a checklist, one item of which is "contains no sentence that asks the implementer to decide". The plan-reviewer also checks blocking edges, file overlap between parallel tickets, and the model assignment, and can only send a plan back, never edit it.

### The project profile

`docs/agents/delivery-profile.md`, written by `setup`, read once per phase and pasted into briefs in extracts. Fields:

- Tracker adapter: Linear MCP, GitHub issues, or files only
- VCS host commands for PR create and complete, and the merge strategy per PR kind (squash for ticket PRs, merge commit for batch PRs)
- Branch model: direct PRs to the integration branch, or a batch branch with one external review per batch
- Test rungs as commands (unit, targeted, authoritative) and which are exclusive resources
- Sandbox conventions per agent: worktree path pattern, port ranges, database naming
- External review tool and its limits (for example, a tool that skips PRs above 150 files)
- Deploy step after merge, watched by run id
- Cleanup exceptions: protected branches, prototype branches, worktrees to keep
- UI hook: whether tickets that touch UI run `impeccable critique` before spec and `impeccable audit` before handoff

Everything project-specific lives here. The skill's own logic never names a tracker, a host or a review tool.

### The orchestrator loop

State lives in files so any phase can resume cold: a human-readable delivery log, a machine-readable `.deliver/state.json` (per ticket: spec path, agent id, phase, head, PR id, grants, last report path), and one report file per agent turn. Agents are told from the start that the orchestrator may vanish and must reach a mergeable state on written rulings.

The loop reacts to agent reports:

- `READY-TO-MERGE`: verify the head (conflict markers, the profile's invariants, the spec's cheap acceptance commands), merge, remove the worktree and both branches, comment on the ticket
- `BLOCKED`: spawn the ruling judge, write the ruling into the spec, resume or respawn the implementer
- silence past a threshold: check the agent is alive; respawn once from the spec and the on-disk state

The orchestrator runs the authoritative test run itself on the merged head, per the profile's cadence (per PR, or per batch), instead of granting slots to agents. Agents run the cheap rung freely and the targeted rung only on what their spec names. The grant protocol remains for resources the profile lists as exclusive.

### Gates and limits

Mandatory regardless of model or ticket size: tests written with the change; one mutation proof per claim; every typecheck the profile lists; the two review axes; content verification on the merged head; the cleanup sweep.

Fixed limits: two full review passes then a closing round; two rulings per ticket then back to planning; one respawn after a dead session; reviewer disagreement is settled by the judge, not the implementer. A small-model PR that fails review on design grounds goes back to the same agent with the ruling first; escalation only when the ruling itself needs design judgment.

Human touchpoints: approve the plan once; be told about merges; deploys follow the profile.

### Post-merge

Cheap acceptance commands re-run on every merged head; the authoritative run per cadence. Then worktree and branch removal locally and remotely (never a forced removal of a dirty tree; anything dirty, detached or without a completed PR is reported instead), the deploy step, the tracker comment with figures, and the cost table.

### The trial

Four small tickets from the originating project, direct PRs to the integration branch with the external review tool per PR, large-model orchestrator. Success criteria, written into the delivery log before the trial starts: cost per merged ticket at or below half of the baseline's large-model tickets; zero findings after merge; at most two review rounds per PR. A small-model orchestrator is a second, separate experiment.

#### Trial result (wave-n-trial, 2026-09-04)

Four tickets, all merged with zero post-merge findings and at most two review rounds each. Weighted tokens (input 1x, cache reads 0.1x, cache writes 2x, output 5x): MSITE-232 12.4M, MSITE-236 9.9M, MSITE-237 14.5M, MSITE-233 31.7M, plus 13.8M of batch-level planning. Against the wave N baseline the large ticket came in a third cheaper than its nearest comparable (MSITE-226, 47.0M, same review-round count), and the small-model implementations cost a third of the comparable large-model ones in raw tokens, at one review round instead of two. The small tickets cost more than their baseline counterparts, because a spec phase of 35-53M raw tokens (two review passes) sat on top of a 20-24M implementation. The lever is the planning phase, not the implementer: a single confirm pass for tickets the plan reviewer already rated small would take most of the gap out.

Defects found in the skill during the trial, fixed: reviewer verdicts delivered only as notifications (now files the implementer polls); reviewer ids unknown to the orchestrator when the implementer spawns reviewers (now listed in READY-TO-MERGE); the state keys `cost.py` attributes by were undocumented (now in `reference/run.md`, and `state.py` warns on others); a broken invariant run (runner stopped, no result line) read as a failure (rerun-once rule).

### Repository layout

```
skills/engineering/deliver/
  SKILL.md            command table and routing
  agents/openai.yaml  interface shim for the installer
  reference/          one playbook per sub-command
  templates/          role agent definitions, the profile, the spec file, the delivery log
  scripts/            state file, cost accounting, sweep, verification helpers
```
