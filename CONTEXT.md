# Deliver

The `deliver` skill takes the ADR and tickets a grilling session produced and runs them to dev: build, review, merge, deploy. These are the words its playbooks, agents and reports use.

## Work

**Ticket**:
A Linear issue that is the whole build input for one implementer: one repository, sized for one sitting, with acceptance criteria, blocking edges, risk tags and a link to the ADR.
_Avoid_: spec, slice, work item

**Risk tag**:
A label on a ticket (auth, concurrency, migration, data loss) that obliges the implementer to write a test for that risk and the final review to read that area in full.
_Avoid_: risk flag, sensitive area

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

**Flag**:
A ticket reviewer's suspicion, unverified, written to the batch's flag log with the implementer's one-line answer.
_Avoid_: finding, issue, comment

**Flag log**:
The batch's flag files, one per ticket, holding each flag and the implementer's answer; the final review reads all of them.
_Avoid_: review notes

**Final review**:
The review of a whole batch on its batch branch by the correctness reviewer and the quality reviewer, followed by at most one fix round.
_Avoid_: gate, PR review

**Finding**:
A defect the final review has verified, with a severity.
_Avoid_: flag, issue

## Roles

**Orchestrator**:
The session the user started, which runs the whole batch and is the only role that talks to the user.
_Avoid_: lead, coordinator

**Implementer**:
The agent that builds one ticket and answers its flags.
_Avoid_: builder, worker

**Ticket reviewer**:
The cheap agent that reads one ticket's diff once and writes flags.
_Avoid_: Haiku reviewer, gate reviewer

**Correctness reviewer**:
The final-review agent that judges whether the batch does what its tickets and ADR say, without bugs.
_Avoid_: spec reviewer

**Quality reviewer**:
The final-review agent that judges the batch against a fixed quality bar of its own, whether or not the repository documents standards; "the existing code does it this way" is never a defence.
_Avoid_: standards reviewer, style reviewer

**Fixer**:
The agent that applies the final review's findings on the batch branch in the one fix round.
_Avoid_: implementer
