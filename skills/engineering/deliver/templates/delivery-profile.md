# Delivery profile

Read by `/deliver`; written by `/deliver setup`. Every field is a fact or a command. Write "none" where a field does not apply.

## Tracker

- Adapter: {linear-mcp | github-issues | files}
- Team or repository: {value}
- Ticket id pattern: {for example MSITE-123}
- Labels the skill sets: {ready-for-agent, in-review}
- Where specs are linked from: {ticket comment | description}

## VCS host

- Host: {azure-devops | github}
- Organisation, project, repository names exactly as the CLI needs them: {values}
- Create PR: `{command with {branch} {target} {title} {body}}`
- Complete PR, ticket kind: `{command}` (strategy: {squash | merge})
- Complete PR, batch kind: `{command}` (strategy: {merge})
- Delete remote branch: `{command}`
- PR state lookup by source branch: `{command}` (used by the sweep)
- PR description limit: {characters}

## Branch model

- Integration branch: {name}
- Batch branch: {none | pattern}, used when: {condition}
- Ticket branch pattern: {feature/{ticket}}
- Multi-PR ticket branch pattern: {feature/{ticket}-{n}}

## Test rungs

| Rung | Command | Duration | Exclusive |
|---|---|---|---|
| unit | `{command}` | {seconds} | no |
| targeted | `{command with {spec}}` | {seconds} | no |
| authoritative | `{command}` | {minutes} | yes |
| {other} | `{command}` | | {yes/no} |

- Authoritative cadence: {per PR | per batch}
- Typechecks (all must pass on the final head): `{commands}`
- Invariants (each a command that fails loudly): `{commands}`
- Dead-declaration detector: `{command, filtered to changed files}`
- Known base flakes and how to attribute them: {list}

## Sandbox conventions

- Worktree path pattern: `{repo}/.worktrees/{ticket}-{side}`
- Port ranges: dev {from-to}; test runner {from-to}
- Database naming: {pattern | none}
- Cache directories that must be per-worktree: {list}
- Dependency install: `{command}`; shared-symlink rule: {text}

## External review tool

- Tool: {name | none}
- Limits: {file count, rate limits, latency}
- Policy: {per ticket PR | per batch PR | never}

## Deploy

- Queue: `{command}` per side
- Watch: `{command with {run-id}}`
- After: {what to verify}

## Cleanup

- Protected branches never deleted: {list}
- Worktrees never removed: {list}
- Sweep rule: PR completed, tree clean, head equals merged commit

## Bookkeeping files edited by every ticket

- {path}: {sentence shape to use}
- {path}: {rule}

## Standards documents reviewers read

- {paths}

## UI hook

- impeccable: {on | off}; when on: `critique` before spec, `audit` before handoff, design authority at {path or URL}

## Delivery log

- Path: {path}

## Baseline for cost comparison

- {figures or "none"}
