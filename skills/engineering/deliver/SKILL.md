---
name: deliver
description: Plan, spec, implement, review, merge and close a batch of tickets with sub-agents at the lowest token cost that keeps quality. Sub-commands setup, plan, spec, run, close, status. Large model for planning, plan review, PR review and rulings; small model for implementation from specs that contain no open judgment.
disable-model-invocation: true
---

# Deliver

`/deliver <command> [arguments]` runs one phase of a delivery. Each phase has a playbook under `reference/`; read the playbook for the command you were given, in full, before doing anything else. Never run a command the user did not name; with no command, print the table below and stop.

| Command | Playbook | Reads | Produces |
|---|---|---|---|
| `setup` | `reference/setup.md` | the repository, its CLAUDE.md, existing tracker docs | `docs/agents/delivery-profile.md`, role agents in `.claude/agents/` |
| `plan <goal \| issue \| spec-file>` | `reference/plan.md` | the profile, the input | a reviewed plan: tickets with blocking edges, file overlap, model per ticket |
| `spec <ticket>` | `reference/spec.md` | the profile, the ticket, the plan | one reviewed spec file per PR |
| `run <ticket...>` | `reference/run.md` | the profile, the specs, `.deliver/state.json` | merged, verified PRs; the delivery log |
| `close` | `reference/close.md` | the state file, the profile | the authoritative run, cleanup, deploy, tracker comments, the cost table |
| `status` | `reference/status.md` | the state file | a table, no model work |

The orchestrator and agent contract is in `reference/protocol.md`; every command that spawns agents reads it too.

## Principles that hold across every command

- **Judgment is written before implementation starts.** A spec is done when no sentence in it asks the implementer to decide. Every decision an implementer or reviewer would otherwise make is a ruling in the spec, and a ruling made later is written back into the spec so it is never made twice.
- **The expensive model judges, the cheap model types.** Role templates in `templates/agents/` fix `model` and `effort` per role; `setup` installs them into the project. Do not spawn a role without its template.
- **Everything project-specific lives in the profile.** The skill's own text never names a tracker, a VCS host, a review tool, a test runner or a branch. `docs/agents/delivery-profile.md` does, and briefs carry extracts of it.
- **State lives in files.** `.deliver/state.json`, the delivery log and one report file per agent turn let any phase resume cold after the orchestrator's session dies. Agents are told this at spawn and must reach a mergeable state on written rulings.
- **Review has a shape and a cap.** Standards and Spec reviewers, spawned fresh with refs only, report verbatim; two full passes, then a closing round, then merge. Mechanical checks (mutation proofs, budget arithmetic, unused-locals, conflict-marker grep, invariants from the profile) are not review findings; they run before review.
- **Nothing is deleted without a counterpart.** A test, an assertion or a file removed from the work must have a replacement named in the spec's migration map or a written ruling that it stays. Caps in tickets are targets; a justified overshoot beats a coverage loss.
- **Merge, verify, clean.** After every merge: content verification on the merged head, the profile's cheap acceptance commands, removal of the worktree and both branches, the tracker comment. The authoritative run happens at the profile's cadence, run by the orchestrator, never by an agent on its own initiative.
- **Measure.** `scripts/cost.py` sums tokens per phase per ticket from the session files; `close` writes the table into the delivery log. Quality is tracked beside it as findings per PR and defects found after merge.

## Skills this one calls

Call them by name through the Skill tool where the playbook says so: `grilling` and `to-spec` when `plan` receives a bare goal, `to-tickets` for the ticket split, `tdd` inside the implementer template, `diagnosing-bugs` and `resolving-merge-conflicts` when an implementer hits their triggers, `codebase-design` when the planner cuts a seam, `impeccable` when the profile's UI hook is on. The Pocock `code-review` skill is not called from `run`: the reviewer role templates carry its Standards and Spec split with model control and the round cap added. Do not confuse it with any other skill named `code-review` installed from a plugin.
