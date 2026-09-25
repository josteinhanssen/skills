# deliver setup

Writes the project profile and installs the role agents. Run once per workspace, again when the project changes, and once to migrate a profile written for the old `deliver` (plan, spec, run, close).

## 1. Discover before asking

Look first; ask only what the workspace cannot tell you.

- An existing `docs/agents/delivery-profile.md`: carry every fact over. Drop what the new flow has no use for: spec roots, plan and spec rulings, the volume threshold, grants, lock directories, exclusive resources, the delivery log path, the external review tool, the UI hook.
- Tracker: `docs/agents/issue-tracker.md`, the MCP servers in the session, or files only. Its state names and whether the risk labels exist.
- Repositories: every git repository in the workspace, its `origin` host, and which CLI is signed in (`az repos`, `gh`).
- Branches: the default branch, any long-lived branch the current work integrates into (CLAUDE.md, AGENTS.md, recent PR targets), branch policies and required builds.
- Deploy: pipeline definitions, whether a merge deploys by itself or runs are queued by hand, after-deploy steps.
- Test rungs: `package.json` scripts, solution and project files, validation ladders in CLAUDE.md, durations.
- Sandbox: worktree directories, port ranges, database naming, per-worktree caches.
- Quality: standards documents, and where shared components, helpers and types live.
- Never: prohibitions in CLAUDE.md or AGENTS.md (databases, environments, secrets).

## 2. Interview the gaps

One round of numbered questions in the `grilling` format, each with a recommended answer, only for fields discovery left empty or ambiguous. Typical gaps: who may vote on a batch PR, the size thresholds, the risk labels, the deploy's after-steps.

## 3. Write the profile

Fill `templates/delivery-profile.md` and write it to `docs/agents/delivery-profile.md`. Every field is a fact or a complete command; "none" where it does not apply.

## 4. Install the role agents

Remove any old `deliver-*` agents from the project's `.claude/agents/` (planner, plan-reviewer, judge, implementer-escalation, reviewer-spec, reviewer-standards). Copy the five templates from `templates/agents/`, keeping their frontmatter (`model`, `effort`, `tools`). Replace each `{profile extract}` marker with the profile fields it names, and every `scripts/` reference with the absolute path of the installed skill's `scripts/` directory. Add no other project prose; the templates are the contract and the profile is the data.

Newly installed agents can take a few minutes to register in a running session. Retry the spawn by name before anything else.

## 5. Check the user's settings

Read `~/.claude/settings.json`. Recommend, and set only with the user's yes:

- `autoCompactWindow: 300000`, so no session or agent drags more than 300k tokens of context through every call;
- `autoContinueAtUsageLimit: true`, so a batch waits out a 5-hour limit and continues on its own.

## 6. The state directory

Create `.deliver/` at the workspace root. If the workspace root is a git repository, add `.deliver/` to `.git/info/exclude`; it is never committed.

## 7. Report

What was discovered, what was asked, the profile path, the installed agents, the settings changed, and anything the user should verify by hand (a CLI not signed in, a pipeline id guessed from a name).
