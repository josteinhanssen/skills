# Implementer brief (filled by the orchestrator at spawn)

Implement the spec `{spec-path}` in `{repository-path}`. Read the spec in full, then the batch-wide rulings in `{plan-path}` under "Batch-wide rulings", then the ruling file `{rulings-path}` if it exists; your template carries the profile extract.

Base: `{base-branch}` at its current head (`git fetch` first; it is `{base-head}` or later; every number in your PR comes from your own measurement on your head, never from the spec's figures). Branch `{ticket-branch}`; worktree `{worktree-path}`; {sandbox-assignment: ports, database, cache directory}. Dependencies: {dependency rule from the profile}.

Out of scope unless the spec names them (report, do not fix): {known base-branch defects}.

PR: target `{base-branch}` with the profile's create command; title `{ticket}: {spec one-line summary}`; body under the host's size cap with acceptance results and the mutation proofs, long tables in a PR comment.

Reviews: after the first push, spawn one `deliver-reviewer-spec` and one `deliver-reviewer-standards` (`fork_turns: "none"`; refs, changed-file list, spec path and your totals only, never your transcript). They write their VERDICT to `.deliver/reports/{ticket}-spec-<pass>.md` and `.deliver/reports/{ticket}-standards-<pass>.md`; poll those files, never idle on a notification. Take every valid finding, push once, spawn fresh reviewers for pass 2 with pass 1's verdict file and the incremental range; closing round after each reviewer's second full pass. {external review tool rule from the profile, with its timeout}.

Exclusive resources: write READY-FOR-RUN to your report file, then `scripts/wait-grant.sh {resource} <your-agent-id>`; one grant covers one run.

When both axes are clean and the external tool has answered or timed out, report READY-TO-MERGE at once: write it to `.deliver/reports/{ticket}-<n>.md` and return it as your final message, listing the agent id of every reviewer you spawned per pass; then {tracker completion rule from the profile}. The orchestrator cannot message you mid-task: resolve on the written rulings; BLOCKED only for a decision the spec and the rulings cannot answer. Stand down with the worktree clean at the pushed head and no listener on your ports; the orchestrator removes the worktree and branches.
