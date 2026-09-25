#!/usr/bin/env python3
"""The deliver state file: .deliver/state.json.

Usage (run from the workspace root the profile names):
  state.py init --slug <slug> --adr <path> [--session-dir <dir>] [--session-jsonl <file>]
  state.py batch set key=value [key=value ...]
  state.py repo <name> set key=value [key=value ...]
  state.py ticket <id> set key=value [key=value ...]
  state.py show

Values are strings unless they parse as JSON (numbers, lists, objects, true/false/null), so
`blockedBy=["A-1"]` and `reviewers={"correctness":"x"}` work.

Layout: {"batch": {...}, "repos": {name: {...}}, "tickets": {id: {...}}}. `init` sets
`batch.startedAt`; `batch set phase=delivered` also sets `batch.closedAt`. `init` moves an
existing state file into .deliver/archive/ when its batch is delivered or it was written by
deliver-v1 (no `repos` key), and refuses while a batch is open. `state.py` accepts any
key, but warns on one outside reference/run.md's State keys table, since `cost.py` and `status`
read only those.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(".deliver/state.json")
ARCHIVE = Path(".deliver/archive")

KNOWN_BATCH_KEYS = {
    "slug", "adr", "phase", "startedAt", "closedAt", "sessionDir", "sessionJsonl",
    "weeklyAtStart", "weeklyCap", "reviewers", "fixer", "confirm", "followUps",
}
KNOWN_REPO_KEYS = {
    "path", "into", "batchBranch", "baseHead", "scratch", "reviewedHead", "pr",
    "mergedHead", "deployRuns",
}
KNOWN_TICKET_KEYS = {
    "repo", "phase", "blockedBy", "branch", "worktree", "agent", "reviewer", "head",
    "flags", "weeklyAtEnd", "respawns",
}


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8"))


def is_v1(state: dict) -> bool:
    """A state file written by deliver-v1 (plan, spec, run, close) has no `repos` key."""
    return "repos" not in state


def is_open(state: dict) -> bool:
    return not is_v1(state) and state.get("batch", {}).get("phase") != "delivered"


def load() -> dict:
    if not STATE.exists():
        sys.exit(f"no state file at {STATE}; run `state.py init` first")
    state = read()
    if is_v1(state):
        sys.exit(f"{STATE} is a deliver-v1 state file; `state.py init` archives it and starts a batch")
    return state


def archive(state: dict) -> Path:
    slug = state.get("batch", {}).get("slug") or "unnamed"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = ARCHIVE / f"state-{'v1-' if is_v1(state) else ''}{slug}-{stamp}.json"
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    STATE.rename(dest)
    return dest


def save(state: dict) -> None:
    state["updatedAt"] = now()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_sets(target: dict, pairs: list[str], known: set[str]) -> None:
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"expected key=value, got {pair!r}")
        key, raw = pair.split("=", 1)
        if key not in known:
            print(f"warning: {key} is not a key cost.py or status reads (see reference/run.md, State keys)", file=sys.stderr)
        target[key] = parse_value(raw)


def cmd_init(args: argparse.Namespace) -> None:
    if STATE.exists():
        existing = read()
        if is_open(existing):
            batch = existing["batch"]
            sys.exit(
                f"batch {batch.get('slug')} is open (phase {batch.get('phase')}) in {STATE}; "
                "resume it, or set its phase to delivered before starting another"
            )
        print(f"archived the previous state file to {archive(existing)}")
    state = {
        "batch": {
            "slug": args.slug,
            "adr": args.adr,
            "phase": None,
            "startedAt": now(),
            "closedAt": None,
            "sessionDir": args.session_dir,
            "sessionJsonl": args.session_jsonl,
        },
        "repos": {},
        "tickets": {},
    }
    save(state)
    print(f"initialised {STATE} for batch {args.slug}")


def cmd_batch(args: argparse.Namespace) -> None:
    state = load()
    apply_sets(state["batch"], args.pairs, KNOWN_BATCH_KEYS)
    if state["batch"].get("phase") == "delivered" and not state["batch"].get("closedAt"):
        state["batch"]["closedAt"] = now()
    save(state)
    print(json.dumps(state["batch"], indent=2, ensure_ascii=False))


def cmd_repo(args: argparse.Namespace) -> None:
    state = load()
    entry = state["repos"].setdefault(args.name, {})
    apply_sets(entry, args.pairs, KNOWN_REPO_KEYS)
    save(state)
    print(json.dumps({args.name: entry}, indent=2, ensure_ascii=False))


def cmd_ticket(args: argparse.Namespace) -> None:
    state = load()
    entry = state["tickets"].setdefault(args.id, {})
    apply_sets(entry, args.pairs, KNOWN_TICKET_KEYS)
    save(state)
    print(json.dumps({args.id: entry}, indent=2, ensure_ascii=False))


def cmd_show(_: argparse.Namespace) -> None:
    if not STATE.exists():
        sys.exit(f"no state file at {STATE}; run `state.py init` first")
    state = read()
    if is_v1(state):
        batch = state.get("batch", {})
        print(
            f"no open batch: {STATE} is a deliver-v1 state file (batch {batch.get('slug')}, "
            f"phase {batch.get('phase')}); `state.py init` archives it"
        )
        return
    batch = state["batch"]
    if not is_open(state):
        print(f"no open batch: the last one, {batch.get('slug')}, is delivered; `state.py init` archives it")
    print(
        f"batch {batch.get('slug')}  phase {batch.get('phase')}  adr {batch.get('adr')}  "
        f"weekly {batch.get('weeklyAtStart')}->{batch.get('weeklyCap')}  "
        f"started {batch.get('startedAt')}  closed {batch.get('closedAt') or ''}"
    )
    for name, r in state["repos"].items():
        print(
            f"  repo {name:<14} into {r.get('into')}  batchBranch {r.get('batchBranch')}  "
            f"baseHead {str(r.get('baseHead') or '')[:8]}  reviewedHead {str(r.get('reviewedHead') or '')[:8]}  "
            f"pr {r.get('pr')}"
        )
    print()
    header = f"{'ticket':<12} {'repo':<12} {'phase':<10} {'flags':<8} head"
    print(header)
    print("-" * len(header))
    for tid, t in state["tickets"].items():
        flags = t.get("flags")
        flags_str = str(len(flags)) if isinstance(flags, list) else ("" if flags is None else str(flags))
        print(f"{tid:<12} {str(t.get('repo')):<12} {str(t.get('phase')):<10} {flags_str:<8} {str(t.get('head') or '')[:8]}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--slug", required=True)
    p_init.add_argument("--adr", required=True)
    p_init.add_argument("--session-dir")
    p_init.add_argument("--session-jsonl")
    p_init.set_defaults(func=cmd_init)

    p_batch = sub.add_parser("batch")
    batch_sub = p_batch.add_subparsers(dest="action", required=True)
    p_batch_set = batch_sub.add_parser("set")
    p_batch_set.add_argument("pairs", nargs="*")
    p_batch_set.set_defaults(func=cmd_batch)

    p_repo = sub.add_parser("repo")
    p_repo.add_argument("name")
    repo_sub = p_repo.add_subparsers(dest="action", required=True)
    p_repo_set = repo_sub.add_parser("set")
    p_repo_set.add_argument("pairs", nargs="*")
    p_repo_set.set_defaults(func=cmd_repo)

    p_ticket = sub.add_parser("ticket")
    p_ticket.add_argument("id")
    ticket_sub = p_ticket.add_subparsers(dest="action", required=True)
    p_ticket_set = ticket_sub.add_parser("set")
    p_ticket_set.add_argument("pairs", nargs="*")
    p_ticket_set.set_defaults(func=cmd_ticket)

    p_show = sub.add_parser("show")
    p_show.set_defaults(func=cmd_show)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
