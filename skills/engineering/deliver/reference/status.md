# deliver status

Reads `.deliver/state.json` and prints the batch. No agent is spawned and no file is written.

Run `scripts/state.py show` and present:

- The batch: slug, ADR, phase, owner, and the weekly readings at start, cap and end.
- What each role runs on: `scripts/workflow.py settings --slug <slug>`.
- Per repository: integration branch, batch branch, reviewed head, batch PR, deploy runs.
- Per ticket: repository, phase, production lines against the estimate, head, and whether its latest workflow is still running (`scripts/workflow.py agents <run id>`, the last of its `runs`).
- Follow-up tickets filed.
- The last rows of `.deliver/costs.md`.

If the state file is missing, say so and point at `/deliver setup`; do not create one.
