# deliver spec

Turns one ticket into one or more spec files, each executable by the small model without a single open judgment. The planner writes, the plan-reviewer gates, the orchestrator routes.

## Where specs live

`docs/agents/specs/<batch-slug>/<ticket>-<n>.md` (the profile may override the root). One spec per PR; a ticket needing several PRs gets `-1`, `-2`, ... with the blocking order stated. Specs are committed on the base branch while live and deleted by `close` after the PR merges; the ticket's completion comment links the spec's last commit.

## The planner's brief

Give the planner: the ticket, the plan (with its batch-wide rulings), the profile, the repository, and `templates/spec.md`. It fills every section:

- **Goal and non-goals.** One paragraph each. Non-goals name the neighbouring work that is out of scope and where it is ticketed.
- **Model and size.** `small` or `large`, with the reason; files and tests expected; the diff volume in files and changed lines, marked `volume: large` above the profile's threshold (default more than 300 changed lines or more than 8 files), which sets the PR review to one full pass per axis.
- **Rulings.** Every judgment call the implementer or a reviewer could otherwise make, decided: caps and whether they are targets, what stays at which test rung and why, naming, fixture shape, what to do on a base-branch defect found in passing (report, never fix), what an accidental deletion must be checked against.
- **Files to touch** and **files not to touch**, both explicit paths. Shared support files are named with their owner.
- **Tests**, by name, with what each proves and at which rung; for a migration, the map from every removed test to its counterpart or to a written "stays" ruling.
- **Fixtures and harnesses to reuse**, with paths and the one convention for each (how catalogs are typed, how an unmatched request is treated, how a render is scoped).
- **Acceptance checks** as commands, in the order to run them, with the expected shape of a pass.
- **Mutation probes**, one per claim: the edit, the test expected to fail, and the restore rule (reverse the edit, verify byte-identical).
- **Bookkeeping edits**: the ledger row, the budget or counter file, docs; the exact sentence shape where a shared file is edited by several tickets.
- **Out of scope**, with ticket ids.
- **Reviewer focus**: what the Spec reviewer should verify first and what the Standards reviewer should not spend words on.

The planner calls `tdd` for the seam list where the ticket is behaviour, and `impeccable critique` when the profile's UI hook is on and the ticket touches a UI surface.

## The plan-reviewer's gate

The plan-reviewer returns a VERDICT against this checklist and never edits:

- No sentence asks the implementer to decide, choose, judge or consider.
- Every removed test or assertion has a counterpart or a stays-ruling.
- Every acceptance check is a command with a stated pass shape.
- Every mutation probe names its edit and its expected failure.
- Files to touch are sufficient for the goal and disjoint from other parallel specs except where the plan states the merge order.
- Fixtures and harnesses named exist at the stated paths on the base branch.
- The model choice matches the ruling count and the blast radius; the volume mark matches the estimated diff.

One pass. The planner applies every finding; the orchestrator verifies closure on the delta and spawns a confirm pass only after a Blocking finding. A spec the confirm pass still faults goes back to `plan` with the findings.

One planner per spec file at a time. When two tickets' fix rounds would both edit one spec file (a cross-ticket seam such as a shared helper, an enum, a hook name), the orchestrator either runs the second fix round after the first's delta is in, with that delta named in its brief, or rules the seam itself in `.deliver/rulings/<ticket>.md` and names the ruling in both briefs; two planners writing the same file in parallel produce two truths and a confirm pass that reviews neither.

## Output

The spec path(s), the model per spec, the size, and the rulings added since the plan. Update the tracker ticket with the spec link if the profile has one.
