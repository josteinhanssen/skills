---
status: accepted
---

# Agents fix what is in scope; follow-ups are for the rest

Amends [0001](0001-deliver-builds-from-tickets.md) and [0002](0002-implementers-check-their-own-risks.md). Two rules from those decisions go: an implementer reported a defect it found in passing and never fixed it, and the fix round touched only the batch's own code. Any defect outside those lines became a follow-up in the tracker's backlog.

Now a run fixes whatever is **in scope**: work the ADR's outcome needs, or code the grilling's tickets change or call directly. Added tickets don't widen it.

- An implementer fixes an in-scope defect it finds on its ticket branch, test first, up to about 200 production lines per ticket. It lists each fix under `In passing:` in its commit. A fix in a risk area gets a risk test and a risk-check answer, and the correctness reviewer reads that area in full. A fix that needs a migration is never made in passing. Nor is one in the areas of the ticket building alongside: those go to that implementer's inbox or onto the carry list.
- The final review makes every in-scope defect a finding, whoever wrote the code, and the fixer fixes findings of up to about 200 lines each. A delta-only confirm pass reads the fix round when its work outside the batch's code passes about 150 production lines or touches a risk area, as well as after a Blocking finding. A confirm pass's Should-fix and Nit findings go to a continuation fixer in the same round. A Blocking finding it says is still open stops the run.
- In-scope work too big for either becomes an **added ticket**. The agent that found it writes the draft in its final message, the clerk files it, and it goes through intake into a later batch of the same run. A quality refactor gets an added ticket only when a ticket still queued for the ADR builds on that code; otherwise it gets one line in the run report.
- Only out-of-scope work, and work only a person can do or decide, becomes a **follow-up**. One that needs a person is assigned to the user and listed in the run report. The clerk searches open issues before it files one, and comments on a match instead.
- An in-passing fix that turns out to be out of scope stays if it is correct and tested.

## Why

The follow-up loop kept runs from ending. Across Memerix's 32 batches up to 2026-10-16, runs filed about 237 follow-ups, 1.5 per delivered ticket. Of the 134 tickets delivered from b4 on, 60 were earlier batches' follow-ups. Each one sent a fresh implementer to learn code that the agent who filed it already knew, and that implementer's own notes became the next follow-ups.

An agent's context dies with it. Work avoids being learned twice only if the agent that found it does it before it finishes, or writes it down in full for the one that will. An added ticket's draft is that write-up: the finder's acceptance criteria, risk tags and estimate, rather than a one-line note.

The bound on scope keeps a run finite. Scope counts the grilling's tickets only, so an added ticket's implementer can't justify another added ticket outside that line. The weekly cap still stops a run.

## The batch bound and the compact window

In-passing work makes batches bigger at the same ticket count, so the bound came up too. Fitted over the 32 batches, a final review costs about 1.6M weighted tokens plus 0.47M per 1,000 lines, and a fix round about 1.3M plus 0.53M. Two half-size batches cost more than one full one, so splitting doesn't save tokens.

Big batches do strain the correctness reviewer. Its mean peak context goes from 184k at about 520 lines to 242k at about 2,450. It compacted mid-review in b4 and b6, at 263k and 267k, and five more reviews peaked between 255k and 266k. Blocking and Should-fix findings fall from about 10 per 1,000 lines at 500 lines to under 4 above 1,300, a noisy fit with no record of a defect that got past review.

The bound stays at 2,500 lines and 6 tickets, because the goal is fewer batches. Each deliver workspace's `.claude/settings.local.json` sets `autoCompactWindow` to 500000, so reviewers stop compacting. Opus 5.5 has a 1M context and no long-prompt surcharge. The setting can't reach one agent alone: workflow agents ignore their frontmatter, and the workspace is the narrowest scope that works, so the orchestrator gets the bigger window too. The run report records the correctness reviewer's peak context and findings per 1,000 lines. If those show coverage suffering, the bound moves.

## Considered options

- **Keep filing.** Rejected: it is the loop above.
- **Fix everything an agent finds, in scope or not.** Rejected: a run would have no end, and a ticket's tests and risk checks thin out as its diff grows.
- **Side batches with their own reviewers and fixers.** The user's idea, to keep each review small. Rejected: review and fix rounds have a large fixed cost, `state.py` allows one open batch, two batch branches in one repository conflict at delivery, and no reviewer would see a fix next to the code that depends on it. b2's one Blocking race turned up only because one reviewer read the whole batch.
- **A lower batch bound (about 1,200 or 1,500 lines).** It keeps the reviewers further from their limit, at the price of more batches and more PRs completed by hand. Rejected while the goal is fewer batches; it is the next step if the findings measure drops.
- **Approve each added ticket by hand.** Rejected: a question per ticket mid-run is the stop the skill is built to avoid.

## Consequences

- An implementer's commit gains `In passing:`, and its report a line count for that work and a draft for each added ticket. Drafts sit outside the 300- and 900-word caps.
- The fixer may change code the batch didn't write, so `verify-merge.py`'s delta read matters more, and the confirm pass has a second trigger.
- Step 5.3 sorts what the batch found into findings, added tickets and follow-ups. A carry item no reviewer ruled on gets the scope test from the orchestrator: small and in scope becomes a finding for the fixer, too big an added ticket, out of scope a follow-up. When the orchestrator can't tell, it is a follow-up.
- `costs.md` gains a Follow-ups/ticket column, left blank on older rows, against the baseline of 1.5. Its weekly column becomes "Weekly %/ticket during batch (all sessions)", because the reading counts every session that ran over the same days.
- About 142 open issues filed under the old rule stay with the user's triage. The rules apply from the next run on.
- A workspace's installed agents and profile carry the rules only after an update by hand or a new `setup`.
