#!/usr/bin/env python3
"""Render a deliver spawn point as a workflow script, show the roles' models and efforts, and list a
workflow run's agents.

Usage (run from the workspace root the profile names):
  workflow.py render --slug <slug> --step "<step>" --phase <phase> --agent-type <role agent> [--agent-type ...]
                     [--agents-dir <dir>] [--profile <path>]
  workflow.py settings [--slug <slug>] [--agents-dir <dir>] [--profile <path>]
  workflow.py agents <run id | run directory>

Every agent deliver spawns runs inside a Claude Code workflow, so the batch shows in the background
tasks as `deliver <slug> · <step>`, one row per agent. A workflow script's name and phases must be
literals, so `render` writes `.deliver/<slug>/workflows/<step>.js` from `workflows/spawn.js` with
them filled in, and prints its absolute path for the Workflow tool's scriptPath, then each agent
type's model and effort. It writes those into the script too: a workflow agent otherwise runs on
the session's model and effort, whatever its agent type says. Exit 1 when a role agent's file is
missing.

A role's model and effort come from three layers, the later winning field by field:
  default  the role agent's frontmatter (in --agents-dir, default `.claude/agents`, then
           `~/.claude/agents`), as setup installs it;
  profile  the profile's `## Agents` table (`| Role | Model | Effort |`, `default` to keep the
           frontmatter's), for every run in the workspace;
  run      the batch's `agentSettings` in `.deliver/state.json`, `{role: {model, effort}}`, read only
           when the state holds batch --slug.
A role is `implementer`, `correctness-reviewer`, `quality-reviewer`, `fixer` or `tracker-clerk`,
with or without `deliver-`. A model is an alias (opus, sonnet, haiku, fable) or a `claude-` id; an
effort is low, medium, high, xhigh or max. Haiku takes no effort, so a Haiku role drops any it is
given. `settings` prints every role's model and effort and the layer each came from, and exits 1 on
a role, model or effort no layer may hold, naming where it was found.

`agents` prints the run's status and the session that launched it, then one line per agent:
label, agent id, and its status. While the run is `running`, the statuses come from its
`journal.jsonl`: `running` (with the minutes since the agent's transcript last changed), `done` or
`failed`. Once the run has ended, `completed` or `killed`, they come from the end record Claude Code
writes to `<session dir>/workflows/<run id>.json`: `done` (`done, no report` when it returned
nothing), `failed: <error>`, or `killed` for an agent a killed run didn't finish. A run id is looked
up under ~/.claude/projects/, preferring this session ($CLAUDE_CODE_SESSION_ID). A run dies with the
process that launched it and then gets no end record, so a `running` agent whose transcript hasn't
changed for long may belong to a session that stopped or restarted.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

PHASES = ("Build", "Final review", "Fix", "Confirm", "Tracker")
ROLES = ("implementer", "correctness-reviewer", "quality-reviewer", "fixer", "tracker-clerk")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
MODEL = re.compile(r"^(opus|sonnet|haiku|fable|claude-[a-z0-9.-]+)$")
PROFILE = "docs/agents/delivery-profile.md"
STATE = Path(".deliver/state.json")
TEMPLATE = Path(__file__).resolve().parent.parent / "workflows" / "spawn.js"
PROJECTS = Path.home() / ".claude" / "projects"


def find_run_dir(run: str) -> Path | None:
    """The directory holding a workflow run's journal: `<session dir>/subagents/workflows/<run id>/`."""
    path = Path(run)
    if (path / "journal.jsonl").is_file():
        return path.resolve()
    session = os.environ.get("CLAUDE_CODE_SESSION_ID")
    if session:
        for journal in PROJECTS.glob(f"*/{session}/subagents/workflows/{run}/journal.jsonl"):
            return journal.parent
    for journal in PROJECTS.glob(f"*/*/subagents/workflows/{run}/journal.jsonl"):
        return journal.parent
    return None


def session_of(run_dir: Path) -> str | None:
    """The id of the session that launched the run, for a run directory under a session's `subagents/workflows/`."""
    if run_dir.parent.name == "workflows" and run_dir.parents[1].name == "subagents":
        return run_dir.parents[2].name
    return None


def run_record(run_dir: Path) -> dict | None:
    """`<session dir>/workflows/<run id>.json`, which Claude Code writes when a run ends, completed or killed."""
    if not session_of(run_dir):
        return None
    path = run_dir.parents[2] / "workflows" / f"{run_dir.name}.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def run_status(run_dir: Path) -> str:
    """`completed` or `killed` from the run's end record, or `running` while it has none."""
    record = run_record(run_dir)
    return str(record.get("status", "ended")) if record else "running"


def run_agents(run_dir: Path) -> list[dict]:
    """The run's agents in launch order: label, agentId, status, error, report.

    The status is `running`, `done` or `failed` from the journal. Once the run has ended its end
    record decides instead: an agent it didn't finish is `killed` when the run was killed, a failed
    agent carries the record's error, and an agent that never started (its agent type not found)
    keeps its label. `report` is false for a done agent whose result was null."""
    agents: dict[str, dict] = {}
    never_started = 0
    for line in (run_dir / "journal.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue  # a line still being written
        kind, key = entry.get("type"), entry.get("key")
        if kind == "started":
            agents[key] = {"label": entry.get("label", ""), "agentId": entry.get("agentId", ""),
                           "status": "running", "error": "", "report": False}
        elif kind == "result" and key in agents:
            agents[key]["status"] = "done"
            agents[key]["report"] = bool(entry.get("result"))
        elif kind == "failed":
            if key in agents:
                agents[key]["status"] = "failed"
            else:
                never_started += 1
                agents[f"never-started-{never_started}"] = {"label": "(never started)", "agentId": "",
                                                            "status": "failed", "error": "", "report": False}
    record = run_record(run_dir)
    if not record:
        return list(agents.values())
    by_id = {a["agentId"]: a for a in agents.values() if a["agentId"]}
    ended = []
    for entry in record.get("workflowProgress") or []:
        if entry.get("type") != "workflow_agent":
            continue
        agent = by_id.get(entry.get("agentId") or "", {"report": False})
        state = entry.get("state", "")
        if state == "done":
            status = "done"
        elif state == "error":
            status = "failed"
        else:
            status = "killed" if record.get("status") == "killed" else state or "ended"
        ended.append({"label": entry.get("label", ""), "agentId": entry.get("agentId", ""), "status": status,
                      "error": str(entry.get("error") or "").splitlines()[0][:200] if entry.get("error") else "",
                      "report": agent["report"]})
    return ended or list(agents.values())


def frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def role_of(name: str, where: str) -> str:
    role = name.strip().removeprefix("deliver-")
    if role not in ROLES:
        sys.exit(f"{where}: no role {name!r} (roles: {', '.join(ROLES)})")
    return role


def checked(role: str, field: str, value: str, where: str) -> str:
    if field == "model" and not MODEL.match(value):
        sys.exit(f"{where}: {role} model {value!r} is not a model alias (opus, sonnet, haiku, fable) or a claude- id")
    if field == "effort" and value not in EFFORTS:
        sys.exit(f"{where}: {role} effort {value!r} is not one of {', '.join(EFFORTS)}")
    return value


def default_layer(agents_dir: Path) -> dict[str, dict[str, str]]:
    """Each role agent's `model` and `effort` from its frontmatter; a role whose file is missing is left out."""
    layer = {}
    for role in ROLES:
        for directory in (agents_dir, Path.home() / ".claude" / "agents"):
            path = directory / f"deliver-{role}.md"
            if path.is_file():
                fields = frontmatter(path)
                layer[role] = {f: checked(role, f, fields[f], str(path))
                               for f in ("model", "effort") if fields.get(f) and fields[f] != "inherit"}
                break
    return layer


def profile_layer(profile: Path) -> dict[str, dict[str, str]]:
    """The rows of the profile's `## Agents` table, `| Role | Model | Effort |`; `default` keeps the frontmatter's."""
    if not profile.is_file():
        return {}
    layer: dict[str, dict[str, str]] = {}
    inside = False
    for number, line in enumerate(profile.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("## "):
            inside = line.strip() == "## Agents"
            continue
        cells = [c.strip().strip("`") for c in line.strip().strip("|").split("|")]
        if not inside or not line.lstrip().startswith("|") or len(cells) < 3:
            continue
        if cells[0].lower() == "role" or set(cells[0]) <= set("-: "):
            continue
        where = f"{profile}:{number}"
        role = role_of(cells[0], where)
        layer[role] = {
            field: checked(role, field, value, where)
            for field, value in (("model", cells[1]), ("effort", cells[2]))
            if value and value != "default"
        }
    return layer


def run_layer(state_path: Path, slug: str | None) -> dict[str, dict[str, str]]:
    """The batch's `agentSettings` in state, `{role: {model, effort}}`, when the state holds batch `slug`."""
    if not slug or not state_path.is_file():
        return {}
    batch = json.loads(state_path.read_text(encoding="utf-8")).get("batch", {})
    if batch.get("slug") != slug:
        return {}
    where = f"{state_path} agentSettings"
    layer = {}
    for name, fields in (batch.get("agentSettings") or {}).items():
        role = role_of(name, where)
        if not isinstance(fields, dict) or set(fields) - {"model", "effort"}:
            sys.exit(f"{where}: {name} must be {{\"model\": ..., \"effort\": ...}}, got {fields!r}")
        layer[role] = {f: checked(role, f, v, where) for f, v in fields.items() if v}
    return layer


def effective(agents_dir: Path, profile: Path, state_path: Path, slug: str | None) -> dict[str, dict[str, tuple[str, str]]]:
    """Each installed role's model and effort as (value, layer), the later layer winning: default,
    profile, run. Haiku takes no effort, so a Haiku role drops whatever effort a layer gave it."""
    layers = (("default", default_layer(agents_dir)), ("profile", profile_layer(profile)), ("run", run_layer(state_path, slug)))
    settings: dict[str, dict[str, tuple[str, str]]] = {}
    for role in ROLES:
        chosen: dict[str, tuple[str, str]] = {}
        for source, layer in layers:
            for field, value in layer.get(role, {}).items():
                chosen[field] = (value, source)
        if "haiku" in chosen.get("model", ("", ""))[0] and "effort" in chosen:
            del chosen["effort"]
        if role in layers[0][1]:
            settings[role] = chosen
    return settings


def describe(fields: dict[str, tuple[str, str]], field: str) -> str:
    if field in fields:
        value, source = fields[field]
        return f"{value} ({source})"
    if field == "effort" and "haiku" in fields.get("model", ("", ""))[0]:
        return "none (Haiku takes none)"
    return "the session's"


def changed(settings: dict[str, dict[str, tuple[str, str]]]) -> str:
    """The roles a profile or run layer moved off their defaults, as `implementer sonnet medium`; empty when none."""
    parts = []
    for role, fields in settings.items():
        moved = [fields[f][0] for f in ("model", "effort") if f in fields and fields[f][1] != "default"]
        if moved:
            parts.append(" ".join([role, *moved]))
    return ", ".join(parts)


def render(args: argparse.Namespace) -> None:
    settings = effective(Path(args.agents_dir), Path(args.profile), STATE, args.slug)
    roles = {}
    for agent_type in args.agent_type:
        role = role_of(agent_type, "--agent-type")
        if role not in settings:
            sys.exit(f"no role agent {agent_type}.md in {args.agents_dir} or ~/.claude/agents (run /deliver setup)")
        roles[agent_type] = {field: value for field, (value, _) in settings[role].items()}
    literal = lambda value: json.dumps(value, ensure_ascii=False)
    script = (
        TEMPLATE.read_text(encoding="utf-8")
        .replace("__NAME__", literal(f"deliver {args.slug} · {args.step}"))
        .replace("__DESCRIPTION__", literal(f"{args.phase} for batch {args.slug}: {', '.join(args.agent_type)}"))
        .replace("__PHASE__", literal(args.phase))
        .replace("__ROLES__", literal(roles))
    )
    name = re.sub(r"[^a-z0-9]+", "-", args.step.lower()).strip("-") or "spawn"
    out = Path(".deliver") / args.slug / "workflows" / f"{name}.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(script, encoding="utf-8")
    print(out.resolve())
    for agent_type in args.agent_type:
        fields = settings[role_of(agent_type, "--agent-type")]
        print(f"{agent_type}: model {describe(fields, 'model')}, effort {describe(fields, 'effort')}")


def show_settings(args: argparse.Namespace) -> None:
    settings = effective(Path(args.agents_dir), Path(args.profile), STATE, args.slug)
    rows = [("role", "model", "effort")]
    for role in ROLES:
        fields = settings.get(role)
        rows.append((role, "not installed (run /deliver setup)", "") if fields is None
                    else (role, describe(fields, "model"), describe(fields, "effort")))
    widths = [max(len(row[i]) for row in rows) for i in range(2)]
    for row in rows:
        print(f"{row[0]:<{widths[0]}}  {row[1]:<{widths[1]}}  {row[2]}".rstrip())


def agents(args: argparse.Namespace) -> None:
    run_dir = find_run_dir(args.run)
    if not run_dir:
        sys.exit(f"no workflow run {args.run} under {PROJECTS}")
    session = session_of(run_dir)
    whose = "this session" if session and session == os.environ.get("CLAUDE_CODE_SESSION_ID") else "another session"
    print(f"run {run_dir.name}: {run_status(run_dir)}; session {session or 'unknown'} ({whose})")
    for a in run_agents(run_dir):
        status = a["status"]
        transcript = run_dir / f"agent-{a['agentId']}.jsonl"
        if status == "running" and transcript.is_file():
            status += f", last write {int((time.time() - transcript.stat().st_mtime) // 60)} min ago"
        elif status == "done" and not a["report"]:
            status += ", no report"
        elif a["error"]:
            status += f": {a['error']}"
        print(f"{a['label']}\t{a['agentId'] or '-'}\t{status}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_render = sub.add_parser("render")
    p_render.add_argument("--slug", required=True)
    p_render.add_argument("--step", required=True)
    p_render.add_argument("--phase", required=True, choices=PHASES)
    p_render.add_argument("--agent-type", required=True, action="append")
    p_settings = sub.add_parser("settings")
    p_settings.add_argument("--slug", help="include this batch's agentSettings from the state file")
    for p in (p_render, p_settings):
        p.add_argument("--agents-dir", default=".claude/agents")
        p.add_argument("--profile", default=PROFILE)
    p_agents = sub.add_parser("agents")
    p_agents.add_argument("run")
    args = parser.parse_args()
    {"render": render, "settings": show_settings, "agents": agents}[args.command](args)


if __name__ == "__main__":
    main()
