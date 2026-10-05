---
status: accepted
---

# Deliver's agents run in workflows

The user wanted a deliver batch to show in Claude Code's background tasks the way an ultracode workflow does: phases, one row per agent, and each agent's model. Only the Workflow tool puts a run there, and its view shows only the agents its own script spawned. So every agent deliver spawns now runs in a workflow for its spawn point: one per ticket, one for the final review pair, one for the fix round, one for a confirm pass, and one per clerk. `scripts/workflow.py render` writes each script from `workflows/spawn.js`, with its name (`deliver <slug> · <step>`) and each role agent's model and effort filled in. The orchestrator stays the session, as ADR 0001 decided, and launches a workflow where it used to call the Agent tool.

## Considered options

- **A mirror workflow.** One workflow per batch whose Haiku agents wait on `.deliver/state.json` and narrate each change, with deliver itself unchanged. Tested on 2026-10-05 against a fake batch: 8 watchers, about 11k Opus-equivalent tokens each. Rejected by the user: every row was a Haiku watcher, not the agent doing the work.
- **One workflow per batch, with the scheduling in the script.** It would give one entry per batch. Rejected for ADR 0001's reasons: a script can't ask the user, read plan usage for the weekly cap, or hear from the orchestrator while it runs, and a BLOCKED answer needs the grilling this session holds.

## Consequences

- Workflow agents can't be resumed: `ListAgents` doesn't list them, and `SendMessage` finds no transcript for them. Where the playbook resumed an implementer (a missing risk check, a merge conflict, a failed check, a BLOCKED answer), it now launches a continuation: a fresh implementer with the earlier brief, the worktree as it stands, and one thing to do, or the rest of the ticket after a BLOCKED answer or a failure. A continuation reads its ticket and worktree again, so it costs more than a resume did. b5's cost rows show how much.
- A Decision relayed to the ticket building alongside goes into that implementer's inbox file instead of a message. The implementer reads its inbox before its last test run and again before it commits.
- A workflow agent runs on the session's model and effort unless the script passes its own. An agent type alone didn't set them in the test: Explore ran on Opus 5.5 at xhigh, the session's settings. `render` writes each role's model and effort into the script. The frontmatter holds the defaults, the profile's Agents table can change them for a workspace, and a run's `--model` and `--effort` for its batches, recorded in state so a resumed session keeps them. A batch that ran a role off its default says so in its cost row, so the per-ticket averages compare like with like.
- A workflow finds only the agents registered when its session started; a role agent added mid-session was "not found". Setup says to start `/deliver` in a new session after installing agents.
- Workflow agents carry the session's `CLAUDE_CODE_SESSION_ID`, so `state.py` accepts their writes as the owner's. They also find the session's MCP tools (the Linear connector's `save_issue` came back from ToolSearch); b5 checks that the clerk's writes go through.
- Their transcripts live in `subagents/workflows/<run id>/`, next to a journal of each agent's id, label and result. When a run ends, completed or killed, Claude Code also writes `workflows/<run id>.json` in the session directory, with each agent's final state and error. A run that dies with its session process gets neither an end record nor further journal lines, and a restarted session keeps its id, so `workflow.py agents` shows such a run's agents as running; the playbook treats one silent past the profile's threshold as gone. `cost.py` reads the transcripts and counts every agent of a recorded run id on that key's row, in whichever session ran it; `save-report.py --run --label` copies a finished agent's report from there.
