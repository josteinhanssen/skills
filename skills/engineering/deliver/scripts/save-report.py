#!/usr/bin/env python3
"""Save a sub-agent's final message to a file, straight from its transcript.

Usage:
  save-report.py --agent <agent id> --out <path> [--heading "<prefix>"] [--session-dir <dir>]

The final reviewers return their findings as their last message, because the harness refuses
report files written by sub-agents. Copying that message into `findings-*.md` with a Write would
cost the orchestrator the whole report again as output tokens; this script copies it from
`<session dir>/subagents/agent-<id>.jsonl` instead. Without --session-dir it looks the agent up
under ~/.claude/projects/, preferring this session ($CLAUDE_CODE_SESSION_ID).

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


def find_transcript(agent: str, session_dir: str | None) -> Path | None:
    name = f"agent-{agent}.jsonl"
    if session_dir:
        path = Path(session_dir) / "subagents" / name
        return path if path.exists() else None
    projects = Path.home() / ".claude" / "projects"
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session:
        for path in projects.glob(f"*/{session}/subagents/{name}"):
            return path
    for path in projects.glob(f"*/*/subagents/{name}"):
        return path
    return None


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
    parser.add_argument("--agent", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--heading", help="save the last message that starts with this text")
    parser.add_argument("--session-dir")
    args = parser.parse_args()

    transcript = find_transcript(args.agent, args.session_dir)
    if not transcript:
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
