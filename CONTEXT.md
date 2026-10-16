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

**In scope**:
Work the ADR's outcome needs, or that sits in code the grilling's tickets change or call directly. Added tickets don't widen it. Everything else is out of scope, however close it sits.
_Avoid_: in the batch, related, adjacent

**In-passing fix**:
An in-scope defect outside its ticket's own work that the implementer fixes on its ticket branch, test first, and lists in its commit for the final review to read.
_Avoid_: drive-by fix, out-of-scope note

**Added ticket**:
A ticket the run creates itself for in-scope work too big for an in-passing fix or the fix round, written from what the agent that found it reported, linked to the ADR, put through intake like the others and built in a later batch.
_Avoid_: follow-up, spin-off

**Follow-up**:
A ticket in the tracker's backlog for work that is out of scope, or that only a person can do or decide; the run never builds it, and one that needs a person is assigned to the user.
_Avoid_: TODO, tech-debt ticket

**Carry list**:
The batch's list of what it has to act on that no diff shows: items a handoff, the grilling or an earlier batch left for this work, and what implementers found but didn't fix. Each item names a ticket or `outside`, and before delivery it is resolved, made a finding, made an added ticket, filed as a follow-up or dropped.
_Avoid_: backlog, notes, TODO list

**Batch**:
The tickets delivered together through one batch branch and one final review.
_Avoid_: wave, release

**Run**:
One `/deliver` invocation, from intake until the last queued ticket is delivered or the weekly cap stops it; it may deliver several batches, and tickets it doesn't reach wait for a later run.
_Avoid_: session, deliver session

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
An in-scope defect the final review has verified, with a severity; the fixer fixes it whether or not the batch wrote that code. An out-of-scope defect is a follow-up, not a finding.
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
