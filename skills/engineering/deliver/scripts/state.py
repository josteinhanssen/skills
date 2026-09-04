#!/usr/bin/env python3
"""The deliver state file: .deliver/state.json.

Usage (run from the repository root):
  state.py init <batch-slug> --base <branch> --head <sha>
  state.py ticket <id> set key=value [key=value ...]      # fields per ticket
  state.py ticket <id> get [key]
  state.py batch set key=value [...]
  state.py grant <resource> <agent-id> | release <resource>
  state.py show                                            # table for `deliver status`
  state.py path                                            # print the file path

Values are strings unless they parse as JSON (numbers, lists, objects, true/false/null).
The file is small and rewritten whole; every write records `updatedAt`.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

KNOWN_TICKET_KEYS = {"spec","model","phase","pr","head","merged","sandbox","rounds","rulings","findingsAfterMerge","agent","plannerAgents","reviewerAgents","judgeAgents","implementerAgents","specReview","report"}

STATE = Path(".deliver/state.json")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load() -> dict:
    if not STATE.exists():
        sys.exit(f"no state file at {STATE}; run `deliver setup` or `state.py init`")
    return json.loads(STATE.read_text(encoding="utf-8"))


def save(state: dict) -> None:
    state["updatedAt"] = now()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def parse_value(raw: str):
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw


def apply_sets(target: dict, pairs: list[str], warn_unknown: bool = False) -> None:
    for pair in pairs:
        if "=" not in pair:
            sys.exit(f"expected key=value, got {pair!r}")
        key, raw = pair.split("=", 1)
        if warn_unknown and key not in KNOWN_TICKET_KEYS:
            print(f"warning: {key} is not a key cost.py or status reads (see reference/run.md, State keys)", file=sys.stderr)
        target[key] = parse_value(raw)


def cmd_init(args: list[str]) -> None:
    if not args:
        sys.exit("init needs a batch slug")
    slug, opts = args[0], args[1:]
    base = head = None
    while opts:
        flag = opts.pop(0)
        if flag == "--base":
            base = opts.pop(0)
        elif flag == "--head":
            head = opts.pop(0)
        else:
            sys.exit(f"unknown option {flag}")
    state = {
        "batch": {"slug": slug, "base": base, "head": head, "createdAt": now(), "runOfRecord": None},
        "tickets": {},
        "grants": {},
        "followUps": [],
    }
    if STATE.exists():
        sys.exit(f"{STATE} exists; refusing to overwrite")
    save(state)
    print(f"initialised {STATE} for batch {slug}")


def cmd_ticket(args: list[str]) -> None:
    if len(args) < 2:
        sys.exit("ticket <id> set|get ...")
    ticket, action, rest = args[0], args[1], args[2:]
    state = load()
    entry = state["tickets"].setdefault(
        ticket,
        {"spec": None, "model": None, "phase": "planned", "agent": None, "pr": None, "head": None,
         "rounds": 0, "rulings": 0, "lastReport": None, "merged": None},
    )
    if action == "set":
        apply_sets(entry, rest, warn_unknown=True)
        save(state)
        print(json.dumps({ticket: entry}, indent=2, ensure_ascii=False))
    elif action == "get":
        print(json.dumps(entry.get(rest[0]) if rest else entry, indent=2, ensure_ascii=False))
    else:
        sys.exit(f"unknown ticket action {action}")


def cmd_batch(args: list[str]) -> None:
    state = load()
    if args and args[0] == "set":
        apply_sets(state["batch"], args[1:])
        save(state)
    print(json.dumps(state["batch"], indent=2, ensure_ascii=False))


def cmd_grant(args: list[str]) -> None:
    if len(args) != 2:
        sys.exit("grant <resource> <agent-id>")
    resource, agent = args
    state = load()
    holder = state["grants"].get(resource)
    if holder:
        sys.exit(f"{resource} is held by {holder['agent']} since {holder['since']}")
    state["grants"][resource] = {"agent": agent, "since": now()}
    save(state)
    print(f"granted {resource} to {agent}")


def cmd_release(args: list[str]) -> None:
    if len(args) != 1:
        sys.exit("release <resource>")
    state = load()
    removed = state["grants"].pop(args[0], None)
    save(state)
    print(f"released {args[0]}" if removed else f"{args[0]} was not held")


def cmd_show(_: list[str]) -> None:
    state = load()
    batch = state["batch"]
    print(f"batch {batch['slug']}  base {batch['base']} @ {batch['head']}  updated {state.get('updatedAt')}")
    if batch.get("runOfRecord"):
        print(f"run of record: {batch['runOfRecord']}")
    print()
    header = f"{'ticket':<12} {'phase':<14} {'model':<6} {'agent':<18} {'pr':<6} {'head':<9} {'rounds':<6} {'rulings':<7} last report"
    print(header)
    print("-" * len(header))
    for tid, t in state["tickets"].items():
        print(
            f"{tid:<12} {str(t.get('phase')):<14} {str(t.get('model')):<6} {str(t.get('agent')):<18} "
            f"{str(t.get('pr')):<6} {str(t.get('head') or '')[:8]:<9} {str(t.get('rounds')):<6} "
            f"{str(t.get('rulings')):<7} {t.get('lastReport') or ''}"
        )
    if state["grants"]:
        print()
        for resource, holder in state["grants"].items():
            print(f"grant {resource}: {holder['agent']} since {holder['since']}")
    if state["followUps"]:
        print()
        for item in state["followUps"]:
            print(f"follow-up: {item}")


COMMANDS = {
    "init": cmd_init,
    "ticket": cmd_ticket,
    "batch": cmd_batch,
    "grant": cmd_grant,
    "release": cmd_release,
    "show": cmd_show,
    "path": lambda _: print(STATE),
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        sys.exit(__doc__)
    COMMANDS[sys.argv[1]](sys.argv[2:])
