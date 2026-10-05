# Deliver

The `deliver` skill takes the ADR and tickets a grilling session produced and runs them to dev: build, review, merge, deploy. These are the words its playbooks, agents and reports use.

## Work

**Ticket**:
A Linear issue that is the whole build input for one implementer: one repository, sized for one sitting, with acceptance criteria, blocking edges, risk tags and a link to the ADR.
_Avoid_: spec, slice, work item

**Risk tag**:
A label on a ticket (auth, concurrency, migration, data loss) that obliges the implementer to write a test for that risk and answer its risk check, and the final review to read that area in full.
_Avoid_: risk flag, sensitive area

**Risk checks**:
The implementer's answers, in its commit message, to the questions its ticket's risk tags raise and to the three it always answers (inputs, existing paths, reuse); the correctness reviewer checks each one against the code.
_Avoid_: self-review, checklist

**Carry list**:
The batch's list of what it has to act on that no diff shows: follow-ups from a handoff, the grilling or an earlier batch, and out-of-scope notes from implementers. Each item names a ticket or `outside`, and is resolved, filed or dropped before delivery.
_Avoid_: backlog, notes, TODO list

**Batch**:
The tickets delivered together through one batch branch and one final review.
_Avoid_: wave, release

**Delivered**:
Merged to the integration branch and running in the environment that branch deploys to, when it deploys anywhere.
_Avoid_: done, shipped, merged

## Branches

**Integration branch**:
The branch a project's batches merge into, named in the project's profile; it may be the project's development branch or a long-lived branch for one body of work.
_Avoid_: main, trunk, base branch

**Batch branch**:
The branch, one per repository, that collects a batch's tickets before the batch goes to the integration branch.
_Avoid_: intermediate branch, feature branch

## Review

**Final review**:
The review of a whole batch on its batch branch by the correctness reviewer and the quality reviewer, followed by at most one fix round.
_Avoid_: gate, PR review

**Finding**:
A defect the final review has verified, with a severity.
_Avoid_: flag, issue

## Roles

**Orchestrator**:
The session the user started, which runs the whole batch, owns its state file and is the only role that talks to the user.
_Avoid_: lead, coordinator

**Implementer**:
The agent that builds one ticket and answers its risk checks.
_Avoid_: builder, worker

**Correctness reviewer**:
The final-review agent that judges whether the batch does what its tickets and ADR say, without bugs.
_Avoid_: spec reviewer

**Quality reviewer**:
The final-review agent that judges the batch against a fixed quality bar of its own, whether or not the repository documents standards; "the existing code does it this way" is never a defence.
_Avoid_: standards reviewer, style reviewer

**Fixer**:
The agent that applies the final review's findings on the batch branch in the one fix round.
_Avoid_: implementer

**Continuation**:
A fresh agent of the same role that carries on an earlier agent's work from its worktree or fix branch, with the earlier brief and either one thing to do or the rest of the work; it takes the place of resuming an agent, which a workflow doesn't allow.
_Avoid_: resume, respawn, follow-up (a follow-up is a ticket)

**Tracker clerk**:
The Haiku agent that makes the tracker writes the orchestrator hands it as a list, so the whole issues a tracker echoes back stay out of the orchestrator's context.
_Avoid_: tracker agent, Linear agent
