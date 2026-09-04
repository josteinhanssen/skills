# deliver plan

Turns a goal, a tracker issue or a spec file into a reviewed plan of tickets. The planner writes; the plan-reviewer judges; the orchestrator (this session) routes between them and never edits the plan itself.

## Input paths

Say which one applies at the start of the output.

1. **A bare goal.** Run `grilling` until the design tree is closed, then `to-spec` to write the spec (published to the tracker if the profile has one). Continue with path 3.
2. **A tracker issue.** Read it and its comments. If it already has the shape of a spec (goal, acceptance criteria, constraints), continue with path 3; otherwise treat its body as a goal and take path 1 with the issue as context.
3. **A spec file.** Spawn the planner.

## The planner's brief

Give the planner: the spec, the whole profile, and the repository. It produces `.deliver/plans/<slug>.md` containing:

- The ticket list from `to-tickets` (tracer-bullet slices with blocking edges), one line each: id or slug, title, blocked-by.
- For every ticket: files it will touch, files it must not touch, the model it needs (`small` unless a ruling count or blast radius says `large`), and a size estimate (files, tests).
- The file-overlap map: any file two parallel tickets both touch, and the order they must merge in.
- Shared seams the tickets will create (a harness, a fixture module, a helper), each with exactly one owning ticket. Two tickets that would each write their own version of the same seam is a plan defect.
- Rulings the whole batch shares (caps and what they mean, what stays at which test rung, naming, what "done" is), so individual specs inherit them.
- Exclusive resources any ticket needs, from the profile.
- The order of implementation and the parallelism it allows.

The planner may call `codebase-design` when cutting a seam and `research` when a fact is outside the repository. It does not write specs; that is `spec`.

## The plan-reviewer's brief

Give the plan-reviewer the plan, the spec, the profile and the checklist below. It returns a VERDICT and never edits.

Checklist:

- Every ticket is a vertical slice with a visible result; blocking edges are complete and acyclic.
- No file is touched by two parallel tickets without a stated merge order.
- Every shared seam has one owner.
- Model assignment is justified by the ruling count and blast radius, not by habit.
- Every batch-wide judgment call is written as a ruling; none is deferred to "the implementer decides".
- Exclusive resources are named where a ticket needs one.
- Nothing in the spec is unaccounted for by a ticket, and no ticket does work the spec did not ask for.

## Rounds

Planner writes, reviewer verdicts, planner takes findings, reviewer confirms. Two passes, then the orchestrator either accepts or sends the plan back with the open findings as a BLOCKED to the user. The plan is approved by the user once; after that, `spec` and `run` do not ask again.

## Output

The plan file path, the ticket table with model and size, the overlap map, and the rulings. If the profile has a tracker, create or update the tickets there with a summary and a link to the plan; the plan file stays the detailed artifact.
