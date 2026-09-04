# {ticket}-{n}: {title}

Model: {small | large} because {reason}. Size: {files} files, {tests} tests. Blocked by: {spec ids or none}.

## Goal

{One paragraph: what is true after this PR merges.}

## Non-goals

{What neighbouring work is out of scope and where it is ticketed.}

## Rulings

{One line each: the decision and its reason. Include the batch-wide rulings that apply. Nothing here asks the implementer to decide.}

- {ruling}

## Files to touch

- `{path}`: {what changes}

## Files not to touch

- `{path}`: {why}

## Tests

| Test (name) | Proves | Rung | File |
|---|---|---|---|
| {name} | {claim} | {unit | targeted | authoritative} | `{path}` |

### Migration map (when tests are removed)

| Removed test | Counterpart | Or stays because |
|---|---|---|

## Fixtures and harnesses to reuse

- `{path}`: {the convention it enforces}

## Acceptance checks

Run in this order on the final head; each line states the shape of a pass.

1. `{command}` → {expected}

## Mutation probes

| Edit | Test expected to fail | Restore |
|---|---|---|
| {file:line, change} | {test name} | reverse the edit; hash byte-identical |

## Bookkeeping edits

- {path}: {exact sentence shape or rule}

## Out of scope, ticketed elsewhere

- {finding}: {ticket id}

## Reviewer focus

- Spec reviewer first checks: {list}
- Standards reviewer need not spend words on: {list}

## Plan-reviewer checklist (ticked by the reviewer, not the planner)

- [ ] No sentence asks the implementer to decide, choose, judge or consider
- [ ] Every removed test has a counterpart or a stays-ruling
- [ ] Every acceptance check is a command with a stated pass shape
- [ ] Every mutation probe names its edit and its expected failure
- [ ] Files to touch suffice and are disjoint from parallel specs except where the plan states the merge order
- [ ] Every named fixture and harness exists on the base branch at the stated path
- [ ] The model choice matches the ruling count and blast radius
