# Delivery profile

Read by `/deliver`; written by `/deliver setup`. Every field is a fact or a copy-pasteable command with placeholders in braces. Write "none" where a field does not apply, so a reader knows it was considered. A sentence about a pipeline, a policy or a gate names the file and line that makes it true.

## Workspace

- Workspace root (holds `.deliver/`): {path}
- ADR location: {path; say if no repository tracks it}

## Tracker

- Adapter: {linear-mcp | github-issues | files}
- Team: {value}
- Ticket id pattern: {for example ATE-123}
- States: in progress {name}; in review {name}; done {name}; backlog {name}
- Write tools (the tracker clerk's): {the server and each tool's own name for moving, commenting on and creating an issue, then the full names last seen (`mcp__<id>__<tool>`; a claude.ai connector's id differs between accounts, and the run finds the current one) | none for a files tracker}
- Risk labels: {risk:auth, risk:concurrency, risk:migration, risk:data-loss}; created by `/deliver` if missing: {yes | no}

## Repositories

One block per repository, in delivery order (the first one's batch PR merges first).

### {name}

- Path: {path}
- Host: {azure-devops | github}; organisation, project and repository exactly as the CLI needs them: {values}
- Integration branch: {branch} (`/deliver --into` overrides it per run)
- Batch branch pattern: `batch/{slug}`
- Ticket branch pattern: `{feature/{ticket}}`
- Fix branch pattern: `fix/{slug}`
- Create PR: `{command with {branch} {target} {title} {body}}`
- PR status (CI and policy builds): `{command with {pr}}`; done when {field and value}
- Vote: `{command}`; who may vote: {the creator's vote counts | a named reviewer, which makes it a stop}
- Complete batch PR: `{command}` (strategy: merge commit or squash, the policy that allows it, and who chose it. With squash, the ticket commits leave the integration branch's history, and the PR description becomes the commit message)
  - By hand, when the permission check refuses the orchestrator's vote: {the option to pick in the host's completion dialog, and the boxes to leave off}
- Required policy builds: {pipeline and the file:line that requires it | none}
- Deploy: {automatic on merge to the integration branch | queued by hand}
  - Queue: `{command}` {or none}
  - Watch: `{command with {run-id} or by commit}`; succeeded when {field and value}
  - After deploy: {steps, e.g. a reseed pipeline, with commands | none}
- PR description limit: {characters}
- Sweep: `scripts/sweep.py --path {path} {host arguments, every one the host needs: --host azure-devops --org {url} --project {project} --repo {repo}, or --host github --repo {owner/name}}`

## Test rungs

| Rung | Repository | Command | Duration |
|---|---|---|---|
| targeted | {repo} | `{command with {file}}` | {seconds} |
| unit | {repo} | `{command}` | {seconds} |
| full | {repo} | `{command}` | {minutes} |

- Typechecks, formatter, linters (all must pass on a final head): `{commands}`
- Invariants (each a command that fails loudly): `{commands | none}`
- Worker cap for an agent's multi-file run: {for example --maxWorkers=4}
- Known flakes and how to attribute them: {list | none}
- Database-backed tests: {how they are marked, the switch that runs them (for example an environment variable naming a migrated database) and what the rungs do without it, e.g. report them as skipped | none}

## Sandbox

- Worktree path pattern: `{repo}/.worktrees/{ticket}`; orchestrator scratch: `{repo}/.worktrees/batch-{slug}`; fixer: `{repo}/.worktrees/fix-{slug}`
- Port ranges: {per purpose}
- Database naming: {pattern per ticket, fixer, correctness reviewer and batch | none}
- Test database: create and migrate `{script command with {database} and {worktree}}`; run a command against it `{script command with {database} and {command}}`; drop `{script command with {database}}`. One script that stops at its first failed step and never prints a connection string {| none}
- Cache directories that must be per worktree: {list}
- Dependency install: `{command}`; symlink rule: {text}
- Silence threshold before a liveness check: {minutes}

## Quality

- Standards documents: {paths | none}
- Shared-code locations reviewers search for reuse: {paths, e.g. components/ui, src/lib}
- File size threshold: {400} lines; function size threshold: {50} lines

## Never

What no agent does in this project, beyond the skill's own rules: {e.g. touch the user's local database, target test or prod branches, queue prod deploys, print .env values}

## Cleanup

- Protected branches never deleted: {list}
- Worktrees never removed: {list}

## Cost baseline

- {figures to compare `.deliver/costs.md` against, or none}
