#!/usr/bin/env python3
"""Tokens per row, from the session's JSONL files.

Usage:
  cost.py --batch <slug> [--session-dir <dir>] [--session-jsonl <file>] [--state .deliver/state.json]
          [--markdown] [--summary-row] [--summary-header]
  cost.py --summary-header

Rows: per ticket "implement" (tickets[id].agent) and, for batches before ADR 0002, "ticket review" (tickets[id].reviewer);
batch "final review" (batch.reviewers plus batch.confirm); "fix" (batch.fixer); "tracker" (batch.clerks); each id key may hold
one id, a list or a map of role to id. An id is an agent id or a workflow run id (`wf_...`), which
stands for every agent in that run (tickets[id].runs holds a ticket's runs);
"orchestrate" (the orchestrator's own transcript, sliced to [batch.startedAt, batch.closedAt or
now]); "unassigned" (any other sub-agent transcript in the session directory, one row each, also
sliced to that window so an earlier or later batch in the same session does not pollute it).

The session directory is `~/.claude/projects/<project>/<session-id>/`: it holds one
`subagents/agent-<id>.jsonl` per sub-agent spawned with the Agent tool, one
`subagents/workflows/<run id>/agent-<id>.jsonl` per agent of a workflow run, next to that run's
`journal.jsonl`, and the orchestrator's own transcript is the sibling `<session-id>.jsonl`. A
recorded run id with no journal in that directory is looked up in every session, since a batch
claimed by a new session holds runs the earlier one launched. The
temporary `tasks/<id>.output` copies are read for any agent missing from `subagents/`. Each is a JSONL transcript with `usage` blocks on assistant messages. The script takes
the directory from --session-dir, the state file's `batch.sessionDir` or $CLAUDE_SESSION_DIR, and
otherwise finds it by looking up the agent and run ids the state file records under ~/.claude/projects/.

Weighted tokens follow the explain-usage convention: input 1x, cache reads 0.1x, cache writes 2x,
output 5x. Assistant messages are deduped by id (a resumed or retried transcript can repeat one).
The opus-eq column further weights each message by a factor read from its own model id, its price
against Opus 5.5's (Haiku 5.5 0.025, or 0.125 on a prompt over 100K tokens; older Haiku 0.25;
sonnet 0.5; opus 1; fable 2.5; unknown 1), so mixed-model batches compare on one scale.

Each row's peak is the largest prompt any of its agents sent in one call (input, cache reads and
cache writes), which is how close it came to its compact window. --markdown and the JSON output
also give the correctness reviewer's peak on its own: the agents labelled `correctness` in
batch.reviewers' runs (the `correctness` id in batches before workflows), continuations included,
confirm passes not. ADR 0004 watches it against the batch bound.

--summary-row prints one markdown row for `.deliver/costs.md`:
  | <YYYY-MM-DD> | <slug> | <tickets> | <weighted total, M> | <weighted per ticket, M> | <opus-eq per ticket, M> | <weekly % per ticket or n/a> | <follow-ups per ticket or n/a> |
Tickets counts the state's tickets except those still `queued`, which a later batch builds; every
per-ticket figure divides by it. The slug cell names every role that ran off its default model or
effort (`ate-488-b6 (implementer sonnet medium)`), from `workflow.py settings` run in this
directory, so a row is averaged only with rows that ran the same settings.
Weekly % per ticket is (batch.weeklyAtEnd - batch.weeklyAtStart) / tickets, falling back to the
latest ticket's weeklyAtEnd when the batch has none; "n/a" without a start and an end. Plan usage
reads in whole percents, so per-ticket readings rarely move; the batch-level end is the one that counts.
The reading covers every session on the account over those days, not this batch alone, and the
header says so. Follow-ups per ticket counts the ids in batch.followUps and batch.needsYou once
each, since a batch may record a needs-you follow-up in either or both, and divides by tickets;
"n/a" when the batch has no followUps key. --summary-header prints that row's header and needs no batch (combine with
--summary-row for a ready-to-append block; alone, it prints the header to start the file with or
to replace an older header with, since rows written before a column existed show it blank).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

from workflow import PROFILE, changed, effective, find_run_dir, run_agents

WEIGHTS = {"input": 1.0, "cache_read": 0.1, "cache_write": 2.0, "output": 5.0}
MODEL_FACTORS = (("haiku", 0.25), ("sonnet", 0.5), ("opus", 1.0), ("fable", 2.5))
# Haiku 5.5 has two rate cards, chosen by prompt length: $0.10 per MTok input up to 100K prompt
# tokens and $0.50 above, against Opus 5.5's $4. Older Haiku is $1 at any length.
HAIKU_5_5_LONG_PROMPT = 100_000
HAIKU_5_5_FACTORS = (0.025, 0.125)


def model_factor(model_id: str | None, prompt_tokens: int) -> float:
    if not model_id:
        return 1.0
    low = model_id.lower()
    if "haiku-5-5" in low:
        short, long = HAIKU_5_5_FACTORS
        return long if prompt_tokens > HAIKU_5_5_LONG_PROMPT else short
    for name, factor in MODEL_FACTORS:
        if name in low:
            return factor
    return 1.0


def blank_totals() -> dict:
    return {"input": 0, "cache_read": 0, "cache_write": 0, "output": 0, "turns": 0, "opus_eq": 0.0, "peak": 0}


def merge_into(target: dict, totals: dict) -> None:
    for key in ("input", "cache_read", "cache_write", "output", "turns"):
        target[key] += totals.get(key, 0)
    target["opus_eq"] += totals.get("opus_eq", 0.0)
    target["peak"] = max(target["peak"], totals.get("peak", 0))


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
            totals["peak"] = max(totals["peak"], inp + cread + cwrite)
            model_id = (message or {}).get("model") if isinstance(message, dict) else None
            msg_weighted = inp * WEIGHTS["input"] + cread * WEIGHTS["cache_read"] + cwrite * WEIGHTS["cache_write"] + out * WEIGHTS["output"]
            totals["opus_eq"] += msg_weighted * model_factor(model_id, inp + cread + cwrite)
    return totals


def weighted(t: dict) -> float:
    return sum(t[k] * w for k, w in WEIGHTS.items())


def raw(t: dict) -> int:
    return int(round(t["input"] + t["cache_read"] + t["cache_write"] + t["output"]))


def load_state(path: Path) -> dict:
    if not path.exists():
        sys.exit(f"no state file at {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def agent_ids(value) -> list[str]:
    """An id key as orchestrators write it: one id, a list of ids, or a map of role to id."""
    if not value:
        return []
    if isinstance(value, dict):
        value = list(value.values())
    return [value] if isinstance(value, str) else [v for v in value if isinstance(v, str)]


def build_mapping(state: dict, runs: dict[str, list[str]] | None = None) -> dict[str, str]:
    """agent id -> row label, first assignment wins. A workflow run id found in `runs` claims each
    of its agents; one not found there stays in the mapping as it is."""
    mapping: dict[str, str] = {}
    runs = runs or {}

    def claim(value, row) -> None:
        for agent_id in agent_ids(value):
            for one in runs.get(agent_id, [agent_id]):
                mapping.setdefault(one, row)

    for tid, entry in state.get("tickets", {}).items():
        claim(entry.get("runs"), f"{tid} implement")
        claim(entry.get("agent"), f"{tid} implement")
        claim(entry.get("reviewer"), f"{tid} ticket review")
    batch = state.get("batch", {})
    claim(batch.get("reviewers"), "(batch) final review")
    claim(batch.get("confirm"), "(batch) final review")
    claim(batch.get("fixer"), "(batch) fix")
    claim(batch.get("clerks"), "(batch) tracker")
    return mapping


def correctness_agents(state: dict, labels: dict[str, dict[str, str]]) -> list[str]:
    """The correctness reviewer's agent ids: the agents labelled `correctness` in each run on
    batch.reviewers, or the map's `correctness` id in batches before workflows."""
    reviewers = state.get("batch", {}).get("reviewers")
    if isinstance(reviewers, dict):
        return agent_ids(reviewers.get("correctness"))
    return [
        agent_id
        for run in agent_ids(reviewers)
        for agent_id, label in labels.get(run, {}).items()
        if label == "correctness"
    ]


def row_order(state: dict, extra_rows: list[str]) -> list[str]:
    order = []
    for tid in state.get("tickets", {}):
        order.append(f"{tid} implement")
        order.append(f"{tid} ticket review")
    order += ["(batch) final review", "(batch) fix", "(batch) tracker", "(batch) orchestrate"]
    order += sorted(extra_rows)
    return order


def summary_header() -> str:
    header = (
        "| Date | Slug | Tickets | Weighted (M) | Weighted/ticket (M) | Opus-eq/ticket (M) "
        "| Weekly %/ticket during batch (all sessions) | Follow-ups/ticket |"
    )
    sep = "|---|---|---|---|---|---|---|---|"
    return f"{header}\n{sep}"


def summary_row(state: dict, batch_slug: str, rows_totals: dict[str, dict], state_path: Path) -> str:
    batch = state.get("batch", {})
    slug = batch.get("slug", batch_slug)
    moved = changed(effective(Path(".claude/agents"), Path(PROFILE), state_path, slug))
    tickets = state.get("tickets", {})
    n = sum(1 for entry in tickets.values() if entry.get("phase") != "queued")
    weighted_total = sum(weighted(t) for t in rows_totals.values())
    opus_total = sum(t.get("opus_eq", 0.0) for t in rows_totals.values())
    date = (batch.get("closedAt") or batch.get("startedAt") or "")[:10]
    weighted_m = weighted_total / 1_000_000
    weighted_per_ticket_m = weighted_m / n if n else 0.0
    opus_per_ticket_m = (opus_total / 1_000_000) / n if n else 0.0

    weekly_at_start = batch.get("weeklyAtStart")
    weekly_at_end = batch.get("weeklyAtEnd")
    if weekly_at_end is None:
        for entry in tickets.values():
            if entry.get("weeklyAtEnd") is not None:
                weekly_at_end = entry["weeklyAtEnd"]
    if n and weekly_at_start is not None and weekly_at_end is not None:
        weekly_pct = f"{(weekly_at_end - weekly_at_start) / n:.2f}%"
    else:
        weekly_pct = "n/a"
    follow_ups = batch.get("followUps")
    if n and isinstance(follow_ups, list):
        filed = {str(i) for i in follow_ups} | {str(i) for i in batch.get("needsYou") or []}
        follow_ups_per_ticket = f"{len(filed) / n:.2f}"
    else:
        follow_ups_per_ticket = "n/a"

    return (
        f"| {date} | {slug}{f' ({moved})' if moved else ''} | {n} | {weighted_m:.2f} | "
        f"{weighted_per_ticket_m:.2f} | {opus_per_ticket_m:.2f} | {weekly_pct} | {follow_ups_per_ticket} |"
    )


def agent_transcripts(session_dir: Path) -> dict[str, Path]:
    """Sub-agent transcripts by agent id: the durable `subagents/agent-<id>.jsonl` under the
    project's session directory first, then the temporary `tasks/<id>.output` for any id not
    found there (the temporary copies do not survive a reboot)."""
    found: dict[str, Path] = {}
    for path in sorted((session_dir / "subagents").glob("agent-*.jsonl")):
        found[path.stem.removeprefix("agent-")] = path
    for path in sorted((session_dir / "subagents" / "workflows").glob("*/agent-*.jsonl")):
        found.setdefault(path.stem.removeprefix("agent-"), path)
    for path in sorted((session_dir / "tasks").glob("*.output")):
        found.setdefault(path.stem, path)
    return found


def workflow_runs(session_dir: Path) -> dict[str, dict[str, str]]:
    """Each workflow run's agents, agent id -> label, from the run journals in the session directory."""
    return {
        journal.parent.name: {a["agentId"]: a["label"] for a in run_agents(journal.parent) if a["agentId"]}
        for journal in sorted((session_dir / "subagents" / "workflows").glob("*/journal.jsonl"))
    }


def find_session_dir(state: dict) -> Path | None:
    """The session directory holding any agent or run id the state file records, searched across projects."""
    projects = Path.home() / ".claude" / "projects"
    for one_id in build_mapping(state):
        for path in projects.glob(f"*/*/subagents/agent-{one_id}.jsonl"):
            return path.parent.parent
        for path in projects.glob(f"*/*/subagents/workflows/*/agent-{one_id}.jsonl"):
            return path.parents[3]
        for path in projects.glob(f"*/*/subagents/workflows/{one_id}/journal.jsonl"):
            return path.parents[3]
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--batch")
    parser.add_argument("--session-dir")
    parser.add_argument("--session-jsonl", help="the orchestrator's own transcript; default batch.sessionJsonl")
    parser.add_argument("--state", default=".deliver/state.json")
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--summary-row", action="store_true")
    parser.add_argument("--summary-header", action="store_true")
    args = parser.parse_args()
    if args.summary_header and not args.summary_row:
        print(summary_header())
        return
    if not args.batch:
        parser.error("--batch is required, except with --summary-header alone")

    state = load_state(Path(args.state))
    batch = state.get("batch", {})
    session_dir = (
        args.session_dir or batch.get("sessionDir") or os.environ.get("CLAUDE_SESSION_DIR") or find_session_dir(state)
    )
    if not session_dir:
        sys.exit("session directory unknown: no recorded agent id has a transcript under ~/.claude/projects; pass --session-dir")
    transcripts = agent_transcripts(Path(session_dir))
    if not transcripts:
        sys.exit(f"no sub-agent transcripts under {session_dir} (looked in subagents/ and tasks/)")
    window = (batch.get("startedAt"), batch.get("closedAt"))

    labels = workflow_runs(Path(session_dir))
    runs = {run: list(agents) for run, agents in labels.items()}
    for one_id in [i for i in build_mapping(state, runs) if i.startswith("wf_")]:
        run_dir = find_run_dir(one_id)  # a run another session launched before this one claimed the batch
        if run_dir:
            labels[one_id] = {a["agentId"]: a["label"] for a in run_agents(run_dir) if a["agentId"]}
            runs[one_id] = list(labels[one_id])
            for path in sorted(run_dir.glob("agent-*.jsonl")):
                transcripts.setdefault(path.stem.removeprefix("agent-"), path)
        else:
            print(f"warning: workflow run {one_id} has no journal under ~/.claude/projects/", file=sys.stderr)
    mapping = build_mapping(state, runs)
    rows_totals: dict[str, dict] = defaultdict(blank_totals)
    row_agents: dict[str, list[str]] = defaultdict(list)
    agent_peaks: dict[str, int] = {}
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
        agent_peaks[agent_id] = totals["peak"]

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
            "peak": t["peak"],
        })
    correctness_peaks = [agent_peaks[a] for a in correctness_agents(state, labels) if a in agent_peaks]
    correctness_peak = max(correctness_peaks) if correctness_peaks else None

    if args.summary_header:
        print(summary_header())
    if args.summary_row:
        print(summary_row(state, args.batch, rows_totals, Path(args.state)))
    if args.summary_header or args.summary_row:
        return

    if args.markdown:
        print("| Row | Agent(s) | Raw | Weighted | Opus-eq | Peak context |")
        print("|---|---|---|---|---|---|")
        for r in rows:
            print(f"| {r['row']} | {r['agents']} | {r['raw']:,} | {r['weighted']:,} | {r['opus_eq']:,} | {r['peak'] // 1000}k |")
        total_raw = sum(r["raw"] for r in rows)
        total_weighted = sum(r["weighted"] for r in rows)
        total_opus = sum(r["opus_eq"] for r in rows)
        print(f"\nBatch total: raw {total_raw:,}  weighted {total_weighted:,}  opus-eq {total_opus:,}")
        peak = f"{correctness_peak // 1000}k" if correctness_peak is not None else "n/a (no correctness reviewer found)"
        print(f"Correctness reviewer peak context: {peak}")
    else:
        print(json.dumps({"batch": args.batch, "rows": rows, "correctnessPeak": correctness_peak}, indent=2))


if __name__ == "__main__":
    main()
