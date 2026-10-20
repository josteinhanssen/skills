#!/usr/bin/env python3
"""Check a workspace's deliver role agents against the installed skill's templates, and update them.

Usage (run from the workspace root the profile names):
  agents.py check [--agents-dir <dir>]
  agents.py update [--agents-dir <dir>]

Setup installs each role agent as its template from `templates/agents/` with two changes: the
`{profile extract}` marker under `## Profile` becomes the profile fields it names, and each code span
that starts with `scripts/` gets the absolute path of the installed skill's `scripts/` directory.
When the skill is updated and a workspace's agents aren't, a run follows the new playbook with
agents written for the old one, and nothing says so. Three batches in one workspace ran that way.

`check` compares each agent in --agents-dir (default `.claude/agents`) with its template: everything
above `## Profile`, frontmatter included, with any absolute `.../scripts/` path at the start of a
code span read as `scripts/`. It prints one line per role, `current`, `differs (<n> lines)`,
`no Profile section` or `missing`, and exits 1 unless all five are current.

`update` rewrites each agent that differs: the template above `## Profile`, with this skill's
`scripts/` path, and the agent's own Profile section below it, which it never changes. It first
copies the files it rewrites to `.deliver/archive/agents-<UTC timestamp>/`. It then prints each
rewritten role with its template's `{profile extract}` line, so the Profile section can be checked
against what the template now asks for. A missing agent, or one with no Profile section, needs
`/deliver setup`: `update` exits 1 on one and writes nothing.
"""
from __future__ import annotations

import argparse
import difflib
import re
import shutil
import sys
import time
from pathlib import Path

ROLES = ("implementer", "correctness-reviewer", "quality-reviewer", "fixer", "tracker-clerk")
PROFILE_HEADING = "\n## Profile\n"
# This file's directory as invoked, symlinks kept, so agents name the path the skill is installed under.
SCRIPTS = Path(__file__).absolute().parent
TEMPLATES = SCRIPTS.parent / "templates" / "agents"
SCRIPTS_PATH = re.compile(r"`[^`\s]*/scripts/")
EXTRACT = re.compile(r"\{profile extract: [^}]*\}")


def split(text: str) -> tuple[str, str] | None:
    """The text above the `## Profile` heading, heading included, and the Profile section below it."""
    above, heading, below = text.partition(PROFILE_HEADING)
    return (above + heading, below) if heading else None


def compare(agents_dir: Path) -> dict[str, tuple[str, int]]:
    """Each role's status (`current`, `differs`, `no Profile section` or `missing`) and its count of differing lines."""
    result = {}
    for role in ROLES:
        path = agents_dir / f"deliver-{role}.md"
        if not path.is_file():
            result[role] = ("missing", 0)
            continue
        agent = split(path.read_text(encoding="utf-8"))
        if agent is None:
            result[role] = ("no Profile section", 0)
            continue
        template, _ = split((TEMPLATES / f"deliver-{role}.md").read_text(encoding="utf-8"))
        installed = SCRIPTS_PATH.sub("`scripts/", agent[0])
        diff = [line for line in difflib.unified_diff(template.splitlines(), installed.splitlines(), lineterm="", n=0)
                if line[:1] in "+-" and not line.startswith(("+++", "---"))]
        result[role] = ("differs", len(diff)) if diff else ("current", 0)
    return result


def check(args: argparse.Namespace) -> None:
    result = compare(Path(args.agents_dir))
    for role, (status, lines) in result.items():
        print(f"{role:<22}{status}{f' ({lines} lines)' if status == 'differs' else ''}")
    stale = [role for role, (status, _) in result.items() if status != "current"]
    if not stale:
        return
    if any(result[role][0] != "differs" for role in stale):
        print("A missing agent, or one with no Profile section, needs /deliver setup.")
    else:
        print(f"The agents differ from the templates in {TEMPLATES}. `agents.py update` rewrites them and keeps each Profile section.")
    sys.exit(1)


def update(args: argparse.Namespace) -> None:
    agents_dir = Path(args.agents_dir)
    result = compare(agents_dir)
    broken = [f"{role} ({status})" for role, (status, _) in result.items() if status in ("missing", "no Profile section")]
    if broken:
        sys.exit(f"{', '.join(broken)} in {agents_dir}: run /deliver setup, which fills a Profile section; nothing was written")
    stale = [role for role, (status, _) in result.items() if status == "differs"]
    if not stale:
        print("All five agents match the templates; nothing was written.")
        return
    backup = Path(".deliver/archive") / f"agents-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
    backup.mkdir(parents=True)
    for role in stale:
        path = agents_dir / f"deliver-{role}.md"
        shutil.copy2(path, backup)
        template, template_profile = split((TEMPLATES / f"deliver-{role}.md").read_text(encoding="utf-8"))
        _, profile = split(path.read_text(encoding="utf-8"))
        path.write_text(template.replace("`scripts/", f"`{SCRIPTS}/") + profile, encoding="utf-8")
        extract = EXTRACT.search(template_profile)
        print(f"updated {role}; its template's Profile asks for: {extract.group(0) if extract else 'nothing'}")
    print(f"The old files are in {backup}. Profile sections were kept as they were.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "update"):
        sub.add_parser(name).add_argument("--agents-dir", default=".claude/agents")
    args = parser.parse_args()
    {"check": check, "update": update}[args.command](args)


if __name__ == "__main__":
    main()
