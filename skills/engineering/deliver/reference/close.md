# deliver close

Closes a batch: the run of record, the batch merge if the profile uses a batch branch, cleanup, deploy, tracker comments, and the cost table. Run when `status` shows every ticket merged.

## 1. Run of record

In the orchestrator's scratch worktree, on the batch head (or the integration head when PRs merged directly): `scripts/verify-head.sh` first, then the profile's authoritative command with default parallelism and a fresh cache directory, JSON output kept under `.deliver/runs/<head>.json`. Record expected, unexpected, flaky, skipped, wall-clock and summed time. Discriminate every unexpected result in isolation before attributing it; a regression stops the close and goes back to `run` as a new ticket.

## 2. Batch merge (batch-branch profiles only)

Open the batch PR into the integration branch with the description template: what moved per ticket, tooling changes, the run-of-record figures, and what is carried but not fixed. State the review of record: if the profile's external review tool will not review the PR (file-count limit, rate limit), say so and name the per-ticket reviews as the record. Complete it with the profile's batch merge strategy, verify the integration head's content equals the batch head, then delete the batch branch.

## 3. Deploy

Queue the profile's deploy step by hand and watch it by run id until it completes. A failed deploy stops the close.

## 4. Cleanup

`scripts/sweep.py --batch` removes every worktree and branch, local and remote, whose PR is completed, whose tree is clean and whose head equals the merged commit; it keeps and reports anything dirty, detached, without a completed PR, or protected by the profile. Check sibling `node_modules` symlinks before each removal. Remove the orchestrator's scratch worktree last. Delete the batch's spec files from the docs tree in one housekeeping commit.

## 5. Tracker and log

On every ticket: the merge commit, the run-of-record figures relevant to it, and the follow-ups filed. Set the tickets to done. Append the close block to the delivery log: outcome table (before, after), the run of record, rulings that shaped the batch, defects the batch caught, follow-ups filed, process changes recorded.

## 6. Cost table

`scripts/cost.py --batch <slug>` sums tokens per phase per ticket from the session files (orchestrator session, each agent's output file) and writes the table into the delivery log: raw and cost-weighted, with review rounds per PR and findings per PR beside them. Compare against the baseline the profile names, if any.

## 7. Report

The outcome table, the run of record, the deploy run id, the cost table, and anything kept or left for the user (a branch the host refused to delete, a worktree with uncommitted work, a tool that needs authorisation).
