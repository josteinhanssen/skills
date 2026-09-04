# deliver status

Reads `.deliver/state.json` and prints the batch. No model work beyond formatting; no agent is spawned and no file is written.

Run `scripts/state.py show` and present:

- The batch: slug, base branch, current integration head, run-of-record figures if any.
- Per ticket: spec path, model, phase (planned, specced, running, at review, ready to merge, merged), agent id and whether alive, PR id and head, review rounds, rulings, last report time.
- Grants: which exclusive resource is held by whom, and the queue.
- Follow-ups reported but not fixed, with ticket ids.
- If `scripts/cost.py --batch <slug>` has run, its latest table.

If the state file is missing, say so and point at `deliver setup`; do not create one.
