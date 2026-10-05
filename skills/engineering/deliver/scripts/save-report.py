#!/usr/bin/env python3
"""Save a sub-agent's final message to a file, straight from its transcript.

Usage:
  save-report.py --agent <agent id> --out <path> [--heading "<prefix>"] [--session-dir <dir>]
  save-report.py --run <workflow run id> --label <label> --out <path> [--heading "<prefix>"]

The final reviewers return their findings as their last message, because the harness refuses
report files written by sub-agents. Copying that message into `findings-*.md` with a Write would
cost the orchestrator the whole report again as output tokens; this script copies it from
`<session dir>/subagents/agent-<id>.jsonl` instead, or from
`<session dir>/subagents/workflows/<run id>/agent-<id>.jsonl` for an agent that ran in a workflow.
Without --session-dir it looks the agent up under ~/.claude/projects/, preferring this session
($CLAUDE_CODE_SESSION_ID). With --run and --label it takes the agent of that label that finished in the
run, and prints its id; exit 1 when that agent is still running, failed or was killed.

An agent may hand its report back through a `SubagentHandback` tool call and then end with a
one-line summary. The report is then that call's `message`, so hand-backs come first: the message
saved is the last hand-back (for a resumed agent, its latest report), else the last assistant
message with text. With --heading it is the last one of those whose text starts with that prefix,
such as "# Correctness findings". A message's text blocks are joined as they stand. Prints the
path, the word count and the first line. Exit 1 when the transcript is missing or no message
matches.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from workflow import find_run_dir, run_agents


def find_transcript(agent: str, session_dir: str | None) -> Path | None:
    name = f"agent-{agent}.jsonl"
    places = (name, f"workflows/*/{name}")
    if session_dir:
        for place in places:
            for path in (Path(session_dir) / "subagents").glob(place):
                return path
        return None
    projects = Path.home() / ".claude" / "projects"
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    for owner in ([session] if session else []) + ["*"]:
        for place in places:
            for path in projects.glob(f"*/{owner}/subagents/{place}"):
                return path
    return None


def agent_of_run(run: str, label: str) -> tuple[str, Path]:
    """The id and transcript of the one agent of that label that finished in the run."""
    run_dir = find_run_dir(run)
    if not run_dir:
        sys.exit(f"no workflow run {run} under ~/.claude/projects/")
    labelled = [a for a in run_agents(run_dir) if a["label"] == label]
    done = [a for a in labelled if a["status"] == "done" and a["agentId"]]
    if not labelled:
        sys.exit(f"run {run} has no agent labelled {label!r}")
    if not done:
        sys.exit(f"run {run}: {label} has not finished ({', '.join(a['status'] for a in labelled)}); no report saved")
    if len(done) > 1:
        sys.exit(f"run {run} has {len(done)} finished agents labelled {label!r}; pass --agent with one of their ids")
    return done[0]["agentId"], run_dir / f"agent-{done[0]['agentId']}.jsonl"


def reports(path: Path) -> tuple[list[str], list[str]]:
    """The agent's hand-back messages, and the text of each assistant message, both in order.

    One assistant message can span several JSONL lines."""
    handbacks: list[str] = []
    messages: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        message = entry.get("message") or {}
        content = message.get("content")
        blocks = [c for c in content if isinstance(c, dict)] if isinstance(content, list) else []
        for block in blocks:
            if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                text = (block.get("input") or {}).get("message", "")
                if isinstance(text, str) and text.strip():
                    handbacks.append(text.strip("\n"))
        texts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
        messages.setdefault(message.get("id") or f"line-{len(messages)}", []).extend(texts)
    joined = ("\n\n".join(b.strip("\n") for b in blocks if b.strip()) for blocks in messages.values())
    return handbacks, [text for text in joined if text]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--agent")
    parser.add_argument("--run")
    parser.add_argument("--label")
    parser.add_argument("--out", required=True)
    parser.add_argument("--heading", help="save the last message that starts with this text")
    parser.add_argument("--session-dir")
    args = parser.parse_args()
    if bool(args.agent) == bool(args.run) or bool(args.run) != bool(args.label):
        parser.error("give --agent, or --run with --label")
    if args.run:
        args.agent, transcript = agent_of_run(args.run, args.label)
        print(f"agent {args.agent}")
    else:
        transcript = find_transcript(args.agent, args.session_dir)
    if not transcript or not transcript.is_file():
        sys.exit(f"no transcript for agent {args.agent} under ~/.claude/projects/ (pass --session-dir)")
    text = None
    for candidates in reports(transcript):
        if args.heading:
            candidates = [m for m in candidates if m.lstrip().startswith(args.heading)]
        if candidates:
            text = candidates[-1]
            break
    if text is None:
        wanted = f"starting with {args.heading!r}" if args.heading else "with text"
        sys.exit(f"agent {args.agent} has no hand-back or message {wanted} ({transcript})")
    out = Path(args.out)
    replaced = " (replaced the existing file)" if out.exists() else ""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    first = text.splitlines()[0][:100]
    print(f"saved {out}{replaced}: {len(text.split())} words; first line: {first}")


if __name__ == "__main__":
    main()
