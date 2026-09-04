#!/usr/bin/env python3
"""Tokens per phase per ticket, from the session's JSONL files.

Usage:
  cost.py --batch <slug> [--session-dir <dir>] [--state .deliver/state.json] [--markdown]

The session directory is where Claude Code keeps this session's transcripts:
the orchestrator's own `<session-id>.jsonl` and one `tasks/<agent-id>.output`
per sub-agent (each a JSONL transcript with `usage` blocks on assistant
messages). By default the script finds it from the state file's `sessionDir`
field, or from `$CLAUDE_SESSION_DIR`.

Each agent id is mapped to a ticket and a phase through the state file: the
ticket's `agent` (implement), `plannerAgents`, `reviewerAgents`, `judgeAgents`
(lists), and batch-level `plannerAgents`. Anything unmapped is reported under
"unassigned" so nothing is silently dropped.

Weighted tokens follow the explain-usage convention: input 1x, cache reads 0.1x,
cache writes 2x, output 5x.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

WEIGHTS = {"input": 1.0, "cache_read": 0.1, "cache_write": 2.0, "output": 5.0}


def usage_of_file(path: Path) -> dict:
    totals = {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "turns": 0}
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
            usage = (message or {}).get("usage") if isinstance(message, dict) else None
            if not usage:
                usage = event.get("usage") if isinstance(event, dict) else None
            if not isinstance(usage, dict):
                continue
            totals["input"] += int(usage.get("input_tokens", 0) or 0)
            totals["cache_read"] += int(usage.get("cache_read_input_tokens", 0) or 0)
            totals["cache_write"] += int(usage.get("cache_creation_input_tokens", 0) or 0)
            totals["output"] += int(usage.get("output_tokens", 0) or 0)
            totals["turns"] += 1
    return totals


def weighted(t: dict) -> float:
    return sum(t[k] * w for k, w in WEIGHTS.items())


def raw(t: dict) -> int:
    return t["input"] + t["cache_read"] + t["cache_write"] + t["output"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--session-dir")
    parser.add_argument("--state", default=".deliver/state.json")
    parser.add_argument("--markdown", action="store_true")
    args = parser.parse_args()

    state = json.loads(Path(args.state).read_text(encoding="utf-8"))
    session_dir = args.session_dir or state.get("batch", {}).get("sessionDir") or os.environ.get("CLAUDE_SESSION_DIR")
    if not session_dir:
        sys.exit("session directory unknown: pass --session-dir or set batch.sessionDir in the state file")
    tasks = Path(session_dir) / "tasks"
    if not tasks.is_dir():
        sys.exit(f"no tasks directory under {session_dir}")

    # agent id -> (ticket, phase)
    mapping: dict[str, tuple[str, str]] = {}
    for agent in state.get("batch", {}).get("plannerAgents", []) or []:
        mapping[agent] = ("(batch)", "plan")
    for ticket, entry in state.get("tickets", {}).items():
        if entry.get("agent"):
            mapping[entry["agent"]] = (ticket, "implement")
        for agent in entry.get("implementerAgents", []) or []:
            mapping[agent] = (ticket, "implement")
        for agent in entry.get("plannerAgents", []) or []:
            mapping[agent] = (ticket, "plan")
        for agent in entry.get("reviewerAgents", []) or []:
            mapping[agent] = (ticket, "review")
        for agent in entry.get("judgeAgents", []) or []:
            mapping[agent] = (ticket, "rulings")

    per = defaultdict(lambda: defaultdict(lambda: {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "turns": 0}))
    for output in sorted(tasks.glob("*.output")):
        agent_id = output.stem
        ticket, phase = mapping.get(agent_id, ("(unassigned)", agent_id))
        totals = usage_of_file(output)
        if totals["turns"] == 0:
            continue
        bucket = per[ticket][phase]
        for key in bucket:
            bucket[key] += totals[key]

    orchestrator = None
    for candidate in Path(session_dir).glob("*.jsonl"):
        orchestrator = usage_of_file(candidate)
        break

    rows = []
    for ticket in sorted(per):
        phases = per[ticket]
        entry = state.get("tickets", {}).get(ticket, {})
        total_raw = sum(raw(t) for t in phases.values())
        total_weighted = sum(weighted(t) for t in phases.values())
        rows.append({
            "ticket": ticket,
            "plan": raw(phases.get("plan", {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0})),
            "implement": raw(phases.get("implement", {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0})),
            "review": raw(phases.get("review", {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0})),
            "rulings": raw(phases.get("rulings", {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0})),
            "other": sum(raw(t) for p, t in phases.items() if p not in ("plan", "implement", "review", "rulings")),
            "raw": total_raw,
            "weighted": round(total_weighted),
            "rounds": entry.get("rounds"),
            "findingsAfterMerge": entry.get("findingsAfterMerge", 0),
        })

    if args.markdown:
        print("| Ticket | Plan | Implement | Review | Rulings | Other | Raw | Weighted | Rounds | Findings after merge |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['ticket']} | {r['plan']:,} | {r['implement']:,} | {r['review']:,} | {r['rulings']:,} | {r['other']:,} | {r['raw']:,} | {r['weighted']:,} | {r['rounds']} | {r['findingsAfterMerge']} |")
        if orchestrator:
            print(f"\nOrchestrator session: raw {raw(orchestrator):,}, weighted {round(weighted(orchestrator)):,}, {orchestrator['turns']} assistant turns.")
    else:
        print(json.dumps({"batch": args.batch, "tickets": rows, "orchestrator": orchestrator}, indent=2))


if __name__ == "__main__":
    main()
