# deliver setup

Produces the project profile and installs the role templates. Run once per repository, and again when the profile changes.

## 1. Discover before asking

Look before interviewing; ask only what the repository cannot tell you.

- Tracker: `docs/agents/issue-tracker.md` if `setup-matt-pocock-skills` ran; otherwise MCP servers available in the session, `.github/`, or nothing (files-only tracker).
- VCS host: the `origin` URL (Azure DevOps, GitHub, other) and which CLI is signed in (`az repos`, `gh`).
- Branch model: the default branch, any long-lived integration branch named in CLAUDE.md, whether a batch branch is in use.
- Test rungs: `package.json` scripts, solution or project files, existing CLAUDE.md validation ladders; which suite is the authoritative one and how long it takes.
- Sandbox conventions: existing worktree directories, port ranges, database naming in CLAUDE.md or agent definitions.
- External review tool: bot comments on recent PRs, their limits (file count, rate limits) if CLAUDE.md records them.
- Deploy: pipeline definitions and how runs are queued and watched.
- Cleanup exceptions: protected branches, prototype or design-authority branches named in docs.
- UI: whether `impeccable` is installed and whether the project has a design authority.

## 2. Interview the gaps

Ask one round of numbered questions with a recommended answer each, in the `grilling` format, only for fields discovery left empty or ambiguous. Typical gaps: the merge strategy per PR kind, the authoritative-run cadence, the review-tool policy, and which resources are exclusive.

## 3. Write the profile

Fill `templates/delivery-profile.md` and write it to `docs/agents/delivery-profile.md`. Every field is a fact or a command, never advice. Commands are complete and copy-pasteable, with placeholders in braces (`{branch}`, `{pr}`, `{port}`). If a field does not apply, write "none" so a later reader knows it was considered.

## 4. Install the role templates

Copy `templates/agents/*.md` into the project's `.claude/agents/`, keeping the `model` and `effort` frontmatter. Replace the `{profile extract}` markers with the profile fields each role needs (implementers: sandbox, test rungs, bookkeeping; reviewers: standards documents and invariants; planner: everything). Do not add project prose beyond those extracts; the templates are the contract and the profile is the data.

## 5. Add the state directory

Create `.deliver/` with `state.json` (from `scripts/state.py init`), `rulings/`, and a `.gitignore` that excludes `reports/`. Add the delivery-log path from the profile if the file does not exist.

## 6. Report

List what was discovered, what was asked, the profile path, the installed agents, and anything the user should verify by hand (a CLI not signed in, a pipeline id guessed from a name).

Say plainly that the role agents register when a session starts: the session that ran `setup` cannot spawn them by name until it is restarted. Until then a phase may run its roles as general-purpose agents with the template body pasted into the brief and the model passed explicitly, which loses the template's `effort` setting; say so in the delivery log when it happens.
