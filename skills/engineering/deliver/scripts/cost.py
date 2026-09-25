#!/usr/bin/env python3
"""Tokens per row, from the session's JSONL files.

Usage:
  cost.py --batch <slug> [--session-dir <dir>] [--session-jsonl <file>] [--state .deliver/state.json]
          [--markdown] [--summary-row] [--summary-header]

Rows: per ticket "implement" (tickets[id].agent) and "ticket review" (tickets[id].reviewer);
batch "final review" (the values of batch.reviewers plus batch.confirm); "fix" (batch.fixer);
"orchestrate" (the orchestrator's own transcript, sliced to [batch.startedAt, batch.closedAt or
now]); "unassigned" (any other sub-agent transcript in the session directory, one row each, also
sliced to that window so an earlier or later batch in the same session does not pollute it).

The session directory is `~/.claude/projects/<project>/<session-id>/`: it holds one
`subagents/agent-<id>.jsonl` per sub-agent, and the orchestrator's own transcript is the sibling
`<session-id>.jsonl`. The temporary `tasks/<id>.output` copies are read for any agent missing from
`subagents/`. Each is a JSONL transcript with `usage` blocks on assistant messages. By default the
script finds the directory from the state file's `batch.sessionDir`, or from $CLAUDE_SESSION_DIR.

Weighted tokens follow the explain-usage convention: input 1x, cache reads 0.1x, cache writes 2x,
output 5x. Assistant messages are deduped by id (a resumed or retried transcript can repeat one).
The opus-eq column further weights each message by a factor read from its own model id (haiku
0.25, sonnet 0.5, opus 1, fable 2.5, unknown 1), so mixed-model batches compare on one scale.

--summary-row prints one markdown row for `.deliver/costs.md`:
  | <YYYY-MM-DD> | <slug> | <tickets> | <weighted total, M> | <weighted per ticket, M> | <opus-eq per ticket, M> | <weekly % per ticket or n/a> |
Weekly % per ticket is (the latest ticket's weeklyAtEnd - batch.weeklyAtStart) / tickets, when
both exist; otherwise "n/a". --summary-header prints that row's header (combine with --summary-row
for a ready-to-append block; use --summary-header alone once, ahead of the file's first row).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

WEIGHTS = {"input": 1.0, "cache_read": 0.1, "cache_write": 2.0, "output": 5.0}
MODEL_FACTORS = (("haiku", 0.25), ("sonnet", 0.5), ("opus", 1.0), ("fable", 2.5))


def model_factor(model_id: str | None) -> float:
    if not model_id:
        return 1.0
    low = model_id.lower()
    for name, factor in MODEL_FACTORS:
        if name in low:
            return factor
    return 1.0


def blank_totals() -> dict:
    return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "turns": 0, "opus_eq": 0.0}


def merge_into(target: dict, totals: dict) -> None:
    for key in ("input", "cache_read", "cache_write", "output", "turns"):
        target[key] += totals.get(key, 0)
    target["opus_eq"] += totals.get("opus_eq", 0.0)


def usage_of_file(path: Path, window: tuple[str | None, str | None] = (None, None)) -> dict:
    totals = blank_totals()
    start, end = window
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            stamp = event.get("timestamp") if isinstance(event, dict) else None
            if isinstance(stamp, str) and ((start and stamp < start) or (end and stamp > end)):
                continue
            message = event.get("message") if isinstance(event, dict) else None
            usage = (message or {}).get("usage") if isinstance(message, dict) else None
            if not usage:
                usage = event.get("usage") if isinstance(event, dict) else None
            if not isinstance(usage, dict):
                continue
            msg_id = (message or {}).get("id") if isinstance(message, dict) else None
            if msg_id:
                if msg_id in seen_ids:
                    continue
                seen_ids.add(msg_id)
            inp = int(usage.get("input_tokens", 0) or 0)
            cread = int(usage.get("cache_read_input_tokens", 0) or 0)
            cwrite = int(usage.get("cache_creation_input_tokens", 0) or 0)
            out = int(usage.get("output_tokens", 0) or 0)
            totals["input"] += inp
            totals["cache_read"] += cread
            totals["cache_write"] += cwrite
            totals["output"] += out
            totals["turns"] += 1
            model_id = (message or {}).get("model") if isinstance(message, dict) else None
            msg_weighted = inp * WEIGHTS["input"] + cread * WEIGHTS["cache_read"] + cwrite * WEIGHTS["cache_write"] + out * WEIGHTS["output"]
            totals["opus_eq"] += msg_weighted * model_factor(model_id)
    return totals


def weighted(t: dict) -> float:
    return sum(t[k] * w for k, w in WEIGHTS.items())


def raw(t: dict) -> int:
    return int(round(t["input"] + t["cache_read"] + t["cache_write"] + t["output"]))


def load_state(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"no state file at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def build_mapping(state: dict) -> dict[str, str]:
    """agent id -> row label, first assignment wins."""
    mapping: dict[str, str] = {}

    def claim(agent_id, row) -> None:
        if agent_id and agent_id not in mapping:
            mapping[agent_id] = row

    for tid, entry in state.get("tickets", {}).items():
        claim(entry.get("agent"), f"{tid} implement")
        claim(entry.get("reviewer"), f"{tid} ticket review")
    batch = state.get("batch", {})
    for agent_id in (batch.get("reviewers") or {}).values():
        claim(agent_id, "(batch) final review")
    for agent_id in batch.get("confirm") or []:
        claim(agent_id, "(batch) final review")
    claim(batch.get("fixer"), "(batch) fix")
    return mapping


def row_order(state: dict, extra_rows: list[str]) -> list[str]:
    order = []
    for tid in state.get("tickets", {}):
        order.append(f"{tid} implement")
        order.append(f"{tid} ticket review")
    order += ["(batch) final review", "(batch) fix", "(batch) orchestrate"]
    order += sorted(extra_rows)
    return order


def summary_header() -> str:
    header = "| Date | Slug | Tickets | Weighted (M) | Weighted/ticket (M) | Opus-eq/ticket (M) | Weekly %/ticket |"
    sep = "|---|---|---|---|---|---|---|"
    return f"{header}\n{sep}"


def summary_row(state: dict, batch_slug: str, rows_totals: dict[str, dict]) -> str:
    batch = state.get("batch", {})
    tickets = state.get("tickets", {})
    n = len(tickets)
    weighted_total = sum(weighted(t) for t in rows_totals.values())
    opus_total = sum(t.get("opus_eq", 0.0) for t in rows_totals.values())
    date = (batch.get("closedAt") or batch.get("startedAt") or "")[:10]
    weighted_m = weighted_total / 1_000_000
    weighted_per_ticket_m = weighted_m / n if n else 0.0
    opus_per_ticket_m = (opus_total / 1_000_000) / n if n else 0.0

    weekly_at_start = batch.get("weeklyAtStart")
    latest_weekly_at_end = None
    for entry in tickets.values():
        if entry.get("weeklyAtEnd") is not None:
            latest_weekly_at_end = entry["weeklyAtEnd"]
    if n and weekly_at_start is not None and latest_weekly_at_end is not None:
        weekly_pct = f"{(latest_weekly_at_end - weekly_at_start) / n:.2f}%"
    else:
        weekly_pct = "n/a"

    return (
        f"| {date} | {batch.get('slug', batch_slug)} | {n} | {weighted_m:.2f} | "
        f"{weighted_per_ticket_m:.2f} | {opus_per_ticket_m:.2f} | {weekly_pct} |"
    )


def agent_transcripts(session_dir: Path) -> dict[str, Path]:
    """Sub-agent transcripts by agent id: the durable `subagents/agent-<id>.jsonl` under the
    project's session directory first, then the temporary `tasks/<id>.output` for any id not
    found there (the temporary copies do not survive a reboot)."""
    found: dict[str, Path] = {}
    for path in sorted((session_dir / "subagents").glob("agent-*.jsonl")):
        found[path.stem.removeprefix("agent-")] = path
    for path in sorted((session_dir / "tasks").glob("*.output")):
        found.setdefault(path.stem, path)
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch", required=True)
    parser.add_argument("--session-dir")
    parser.add_argument("--session-jsonl", help="the orchestrator's own transcript; default batch.sessionJsonl")
    parser.add_argument("--state", default=".deliver/state.json")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--summary-row", action="store_true")
    parser.add_argument("--summary-header", action="store_true")
    args = parser.parse_args()

    state = load_state(Path(args.state))
    batch = state.get("batch", {})
    session_dir = args.session_dir or batch.get("sessionDir") or os.environ.get("CLAUDE_SESSION_DIR")
    if not session_dir:
        sys.exit("session directory unknown: pass --session-dir or set batch.sessionDir in the state file")
    transcripts = agent_transcripts(Path(session_dir))
    if not transcripts:
        sys.exit(f"no sub-agent transcripts under {session_dir} (looked in subagents/ and tasks/)")
    window = (batch.get("startedAt"), batch.get("closedAt"))

    mapping = build_mapping(state)
    rows_totals: dict[str, dict] = defaultdict(blank_totals)
    row_agents: dict[str, list[str]] = defaultdict(list)
    unassigned_rows: list[str] = []

    for agent_id, output in sorted(transcripts.items()):
        row = mapping.get(agent_id)
        if row is None:
            totals = usage_of_file(output, window)
            if totals["turns"] == 0:
                continue
            row = f"(unassigned) {agent_id}"
            unassigned_rows.append(row)
        else:
            totals = usage_of_file(output, (None, None))
            if totals["turns"] == 0:
                continue
        merge_into(rows_totals[row], totals)
        row_agents[row].append(agent_id)

    jsonl = args.session_jsonl or batch.get("sessionJsonl")
    orchestrator = None
    sibling = Path(str(session_dir).rstrip("/") + ".jsonl")
    if jsonl and Path(jsonl).is_file():
        orchestrator = usage_of_file(Path(jsonl), window)
    elif sibling.is_file():
        orchestrator = usage_of_file(sibling, window)
    else:
        for candidate in Path(session_dir).glob("*.jsonl"):
            orchestrator = usage_of_file(candidate, window)
            break
    if orchestrator and orchestrator["turns"]:
        merge_into(rows_totals["(batch) orchestrate"], orchestrator)

    rows = []
    for row in row_order(state, unassigned_rows):
        t = rows_totals.get(row)
        if not t or t["turns"] == 0:
            continue
        rows.append({
            "row": row,
            "agents": ",".join(row_agents.get(row, [])),
            "raw": raw(t),
            "weighted": round(weighted(t)),
            "opus_eq": round(t.get("opus_eq", 0.0)),
        })

    if args.summary_header:
        print(summary_header())
    if args.summary_row:
        print(summary_row(state, args.batch, rows_totals))
    if args.summary_header or args.summary_row:
        return

    if args.markdown:
        print("| Row | Agent(s) | Raw | Weighted | Opus-eq |")
        print("|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['row']} | {r['agents']} | {r['raw']:,} | {r['weighted']:,} | {r['opus_eq']:,} |")
        total_raw = sum(r["raw"] for r in rows)
        total_weighted = sum(r["weighted"] for r in rows)
        total_opus = sum(r["opus_eq"] for r in rows)
        print(f"\nBatch total: raw {total_raw:,}  weighted {total_weighted:,}  opus-eq {total_opus:,}")
    else:
        print(json.dumps({"batch": args.batch, "rows": rows}, indent=2))


if __name__ == "__main__":
    main()
