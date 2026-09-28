#!/usr/bin/env python3
"""Save a sub-agent's final message to a file, straight from its transcript.

Usage:
  save-report.py --agent <agent id> --out <path> [--heading "<prefix>"] [--session-dir <dir>]

The final reviewers return their findings as their last message, because the harness refuses
report files written by sub-agents. Copying that message into `findings-*.md` with a Write would
cost the orchestrator the whole report again as output tokens; this script copies it from
`<session dir>/subagents/agent-<id>.jsonl` instead. Without --session-dir it looks the agent up
under ~/.claude/projects/, preferring this session ($CLAUDE_CODE_SESSION_ID).

The message saved is the last assistant message in the transcript (for a resumed agent, its
latest report), or with --heading the last one whose text starts with that prefix, such as
"# Correctness findings": an agent can add a short summary after its findings when the harness
asks it to hand back. Its text blocks are joined as they stand. Prints the path, the word count
and the first line. Exit 1 when the transcript is missing or no message matches.
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


def assistant_messages(path: Path) -> list[str]:
    """The text of each assistant message in order; one message can span several JSONL lines."""
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
        texts = [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"] if isinstance(content, list) else []
        messages.setdefault(message.get("id") or f"line-{len(messages)}", []).extend(texts)
    joined = ("\n\n".join(b.strip("\n") for b in blocks if b.strip()) for blocks in messages.values())
    return [text for text in joined if text]


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
    messages = assistant_messages(transcript)
    if args.heading:
        messages = [m for m in messages if m.lstrip().startswith(args.heading)]
    if not messages:
        wanted = f"starting with {args.heading!r}" if args.heading else "with text"
        sys.exit(f"agent {args.agent} has no message {wanted} ({transcript})")
    text = messages[-1]
    out = Path(args.out)
    replaced = " (replaced the existing file)" if out.exists() else ""
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text + "\n", encoding="utf-8")
    first = text.splitlines()[0][:100]
    print(f"saved {out}{replaced}: {len(text.split())} words; first line: {first}")


if __name__ == "__main__":
    main()
