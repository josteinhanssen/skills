# deliver spec

Turns one ticket into one or more spec files, each executable by the small model without a single open judgment. The planner writes, the plan-reviewer gates, the orchestrator routes.

## Where specs live

`docs/agents/specs/<batch-slug>/<ticket>-<n>.md` (the profile may override the root). One spec per PR; a ticket needing several PRs gets `-1`, `-2`, ... with the blocking order stated. Specs are committed on the base branch while live and deleted by `close` after the PR merges; the ticket's completion comment links the spec's last commit.

## The planner's brief

Give the planner: the ticket, the plan (with its batch-wide rulings), the profile, the repository, and `templates/spec.md`. It fills every section:

- **Goal and non-goals.** One paragraph each. Non-goals name the neighbouring work that is out of scope and where it is ticketed.
- **Model and size.** `small` or `large`, with the reason; files and tests expected.
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
- The model choice matches the ruling count and the blast radius.

Two passes, then closing. A spec the reviewer still faults after that goes back to `plan` with the findings.

## Output

The spec path(s), the model per spec, the size, and the rulings added since the plan. Update the tracker ticket with the spec link if the profile has one.
