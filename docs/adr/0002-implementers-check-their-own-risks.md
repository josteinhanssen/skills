---
status: accepted
---

# Implementers check their own risks; the Haiku ticket reviewer is dropped

Amends [0001](0001-deliver-builds-from-tickets.md), which had a Haiku ticket reviewer read each ticket's diff once and write flags for the final review to rule on. The ticket reviewer is gone. Each implementer now answers a fixed set of risk checks from the code before it commits: one question per risk tag, plus inputs, existing paths and reuse on every ticket. Its answers go in the commit message under `Risk checks:`, and the correctness reviewer checks each one. Knowledge that no diff shows goes on a carry list, which the final review rules on.

## Why

After trial 1 the ticket reviewer's checks were sharpened, and trial 2 was to decide whether it stayed. Over batches `ate-488-b1`, `b2` and the first four tickets of `b3`, it read 13 tickets:

- On two tickets its flags led to fixes: ATE-522 (a duplicate helper) and ATE-537 (two OpenAPI annotations).
- On b2 it wrote no flag file at all for two tickets, and the orchestrator had to recover them.
- In b2 the final review found four defects in diffs the ticket reviewers had read without flagging them: a regex duplicating `OrgNumbers.IsValid` and a money field with no upper bound (ATE-522), and a removal that went around `GravestoneOrderService` and bare constants (ATE-526).
- The one Blocking defect in b2, an accept or reject racing intake, needed code outside the diff (`OrderFactService`), which a diff-only reviewer never reads.
- In b3 it returned no flags on the auth and concurrency tickets. Their briefs asked it specific questions, which its reports didn't answer by name.

It cost about 2% of b2's Opus-equivalent tokens and 4% of b3's so far. On top of that, each ticket took two or three extra orchestrator calls to spawn it, recover its file and resume the implementer.

The misses have one thing in common: each was a question about the code around the change. Who else writes these rows? Does this field fit its column? Is there a service that already removes this? The implementer has that context already, and the correctness reviewer can check a written answer faster than it can find the question.

## Considered options

- **Keep the Haiku reviewer.** Rejected: sharpening its checks after trial 1 did not change what it caught.
- **Sonnet 5 on risk-tagged tickets only, allowed to read beyond the diff.** Rejected for now. It would cost at least twice as much per ticket, more once it reads beyond the diff, and in b2 the final review caught the one Blocking defect anyway. It is the next step if the risk checks miss what a second reader would have caught.
- **Implementer risk checks, verified by the correctness reviewer.** Chosen.

## Consequences

- Nobody reads a ticket on its own before the final review. The correctness reviewer reads each implementer's answers as claims and searches for other writers of the same rows itself.
- The implementer's report grows from under 200 words to under 300.
- Ticket phases lose `flagged` and `answering`, and flag files are gone. `cost.py` still reads `reviewer` from older state files.
- If a batch's final review finds a defect that a risk-check answer covered wrongly, that goes in the batch's skill notes, and it counts toward the Sonnet option above.
