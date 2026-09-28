#!/usr/bin/env python3
"""The deliver state file: .deliver/state.json.

Usage (run from the workspace root the profile names):
  state.py init --slug <slug> --adr <path> [--session-dir <dir>] [--session-jsonl <file>]
  state.py batch set key=value [key=value ...]
  state.py batch claim [--from <phase>] [--to <phase>]
  state.py repo <name> set key=value [key=value ...]
  state.py ticket <id> set key=value [key=value ...]
  state.py show

Values are strings unless they parse as JSON (numbers, lists, objects, true/false/null), so
`blockedBy=["A-1"]` and `reviewers={"correctness":"x"}` work. `init` stores the ADR path as an
absolute path, since agents working in worktrees read it.

One session owns a batch. `init` records the session's $CLAUDE_CODE_SESSION_ID as `batch.owner`,
and every later write from another Claude Code session is refused until that session runs
`batch claim`, which the playbook has it do only after asking the user. `batch claim --from <p>
--to <p>` also moves the phase, and only when it is still <p>, so a step that must run once (the
close) runs in one session. A state file without an owner, or a shell outside Claude Code, is not
checked. Every write holds a lock on .deliver/state.lock and replaces the file in one rename.

Layout: {"batch": {...}, "repos": {name: {...}}, "tickets": {id: {...}}}. `init` sets
`batch.startedAt`; `batch set phase=delivered` also sets `batch.closedAt`. `init` moves an
existing state file into .deliver/archive/ when its batch is delivered or it was written by
deliver-v1 (no `repos` key), and refuses while a batch is open. `state.py` accepts any
key, but warns on one outside reference/run.md's State keys table, since `cost.py` and `status`
read only those.
"""
from __future__ import annotations

import argparse
import difflib
import fcntl
import json
import os
import sys
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(".deliver/state.json")
LOCK = Path(".deliver/state.lock")
ARCHIVE = Path(".deliver/archive")
SESSION = os.environ.get("CLAUDE_CODE_SESSION_ID") or None

KNOWN_BATCH_KEYS = {
    "slug", "adr", "phase", "owner", "startedAt", "closedAt", "sessionDir", "sessionJsonl",
    "weeklyAtStart", "weeklyCap", "weeklyAtEnd", "mergeConsent", "reviewers", "fixer", "confirm", "followUps",
}
KNOWN_REPO_KEYS = {
    "path", "into", "batchBranch", "baseHead", "scratch", "reviewedHead", "pr",
    "mergedHead", "deployRuns",
}
KNOWN_TICKET_KEYS = {
    "repo", "phase", "blockedBy", "estimate", "branch", "worktree", "agent", "head",
    "prodLines", "weeklyAtEnd", "respawns",
}

# Keys an orchestrator has written where it meant a known one.
KNOWN_MISTAKES = {
    "confirmReviewer": "confirm (a list of agent ids)",
    "confirmReviewers": "confirm (a list of agent ids)",
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


@contextmanager
def locked():
    """Serialise read-modify-write across sessions; the lock is released when the process exits."""
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def check_owner(state: dict) -> None:
    owner = state["batch"].get("owner")
    if owner and SESSION and owner != SESSION:
        sys.exit(
            f"batch {state['batch'].get('slug')} is owned by session {owner}, not this one ({SESSION}). "
            "Another session may still be running it: ask the user, then `state.py batch claim` to take it over"
        )


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
    tmp = STATE.with_name(f"{STATE.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, STATE)


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
            close = KNOWN_MISTAKES.get(key) or next(iter(difflib.get_close_matches(key, sorted(known), n=1)), None)
            hint = f"; did you mean {close}?" if close else ""
            print(f"warning: {key} is not a key cost.py or status reads (see reference/run.md, State keys){hint}", file=sys.stderr)
        target[key] = parse_value(raw)


def cmd_init(args: argparse.Namespace) -> None:
    with locked():
        init(args)


def init(args: argparse.Namespace) -> None:
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
            "adr": str(Path(args.adr).resolve()),
            "phase": None,
            "owner": SESSION,
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
    with locked():
        state = load()
        check_owner(state)
        apply_sets(state["batch"], args.pairs, KNOWN_BATCH_KEYS)
        if state["batch"].get("phase") == "delivered" and not state["batch"].get("closedAt"):
            state["batch"]["closedAt"] = now()
        save(state)
    print(json.dumps(state["batch"], indent=2, ensure_ascii=False))


def cmd_claim(args: argparse.Namespace) -> None:
    with locked():
        state = load()
        batch = state["batch"]
        if args.from_phase and batch.get("phase") != args.from_phase:
            sys.exit(
                f"batch {batch.get('slug')} is in phase {batch.get('phase')}, not {args.from_phase}; "
                "another session has moved it on. Leave it to that session"
            )
        previous = batch.get("owner")
        batch["owner"] = SESSION
        if args.to_phase:
            batch["phase"] = args.to_phase
        save(state)
    taken = f", taken over from {previous}" if previous and previous != SESSION else ""
    print(f"batch {batch.get('slug')} owned by {SESSION}{taken}; phase {batch.get('phase')}")


def cmd_repo(args: argparse.Namespace) -> None:
    with locked():
        state = load()
        check_owner(state)
        entry = state["repos"].setdefault(args.name, {})
        apply_sets(entry, args.pairs, KNOWN_REPO_KEYS)
        save(state)
    print(json.dumps({args.name: entry}, indent=2, ensure_ascii=False))


def cmd_ticket(args: argparse.Namespace) -> None:
    with locked():
        state = load()
        check_owner(state)
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
    def pct(key: str) -> str:
        value = batch.get(key)
        return "-" if value is None else str(value)

    owner = batch.get("owner")
    whose = "" if not owner else " (this session)" if owner == SESSION else " (another session)" if SESSION else ""
    print(
        f"batch {batch.get('slug')}  phase {batch.get('phase')}  adr {batch.get('adr')}  "
        f"weekly start {pct('weeklyAtStart')}, cap {pct('weeklyCap')}, end {pct('weeklyAtEnd')}  "
        f"started {batch.get('startedAt')}  closed {batch.get('closedAt') or ''}"
    )
    print(f"  owner {owner or 'not recorded'}{whose}")
    for name, r in state["repos"].items():
        print(
            f"  repo {name:<14} into {r.get('into')}  batchBranch {r.get('batchBranch')}  "
            f"baseHead {str(r.get('baseHead') or '')[:8]}  reviewedHead {str(r.get('reviewedHead') or '')[:8]}  "
            f"pr {r.get('pr')}"
        )
    print()
    header = f"{'ticket':<12} {'repo':<12} {'phase':<10} {'lines/est':<10} head"
    print(header)
    print("-" * len(header))
    for tid, t in state["tickets"].items():
        lines = f"{t.get('prodLines', '-')}/{t.get('estimate', '-')}"
        print(f"{tid:<12} {str(t.get('repo')):<12} {str(t.get('phase')):<10} {lines:<10} {str(t.get('head') or '')[:8]}")


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
    p_batch_claim = batch_sub.add_parser("claim")
    p_batch_claim.add_argument("--from", dest="from_phase")
    p_batch_claim.add_argument("--to", dest="to_phase")
    p_batch_claim.set_defaults(func=cmd_claim)

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
