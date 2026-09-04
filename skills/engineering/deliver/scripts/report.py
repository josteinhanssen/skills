#!/usr/bin/env python3
"""Extract an agent's final report from its transcript without reading the transcript.

Usage:
  report.py <agent-output-file> [--out <path>] [--wait <seconds>]

Reads the JSONL transcript Claude Code writes for a sub-agent (`tasks/<id>.output`),
finds the last assistant message that ended the turn, and prints its text (or
writes it to --out). With --wait it polls until such a message exists or the
timeout passes. The orchestrator uses this instead of TaskOutput, which would
dump the whole transcript into context.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def final_text(path: Path) -> str | None:
    last = None
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = event.get("message") if isinstance(event, dict) else None
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            if message.get("stop_reason") not in (None, "end_turn"):
                continue
            content = message.get("content")
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text")
            else:
                continue
            if text.strip():
                last = text.strip()
    return last


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("output_file")
    ap.add_argument("--out")
    ap.add_argument("--wait", type=int, default=0)
    args = ap.parse_args()
    path = Path(args.output_file)
    deadline = time.time() + args.wait
    text = None
    while True:
        if path.exists():
            text = final_text(path)
        if text or time.time() >= deadline:
            break
        time.sleep(5)
    if not text:
        sys.exit("no final report found")
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
        print(f"wrote {args.out} ({len(text)} chars)")
    else:
        print(text)


if __name__ == "__main__":
    main()
