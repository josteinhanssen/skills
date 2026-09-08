#!/usr/bin/env python3
"""Pre-merge and post-merge checks for one deliver PR, host-agnostic.

Usage:
  pre-merge.py --ticket <id> --spec <spec.md> --base <ref> --head <ref>
               [--remote origin --head-branch <branch>] [--test-pattern <regex>]
               [--reports .deliver/reports] [--repo <path>]
  pre-merge.py --post --head <pr-head-ref> --merged <merged-ref> [--repo <path>]

Pre-merge checks (exit code = number of failed checks):
  1. the head branch is fetched explicitly (a restricted fetch refspec otherwise leaves it stale)
     and both refs resolve
  2. every changed file is named verbatim in the spec (backticked path); the rest are listed
  3. changed files that are not tests or docs (by --test-pattern) are listed as production
     touches for the orchestrator to check against the spec's Files to touch
  4. the latest Spec and Standards verdict files for the ticket exist and carry no open Blocking
Post-merge (--post): the merged ref's tree is identical to the PR head's (squash or merge commit),
so content verification of the merged head can rely on the head checks already run.
The host's completion command, the authoritative run and the sweep stay with the orchestrator
and the profile.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TEST_PATTERN = r"(\.test\.[cm]?[jt]sx?$|\.spec\.[cm]?[jt]sx?$|(^|/)tests?/|(^|/)docs/|(^|/)__tests__/|budget\.json$|_test\.go$|_test\.py$|(^|/)test_[^/]+\.py$)"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def resolve(repo: Path, ref: str) -> str | None:
    try:
        return git(repo, "rev-parse", "--short", "--verify", f"{ref}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        return None


def latest_verdict(reports: Path, ticket: str, axis: str) -> Path | None:
    candidates = sorted(reports.glob(f"{ticket}-{axis}-*.md"), key=lambda p: (len(p.stem), p.stem))
    return candidates[-1] if candidates else None


def blocking_open(text: str) -> bool:
    match = re.search(r"^#{1,4}\s*\**Blocking\**:?\s*$(.*?)(?=^#{1,4}\s|\Z)", text, re.M | re.S)
    if not match:
        # inline form: "**Blocking**: none" or an APPROVE line
        inline = re.search(r"\*\*Blocking\*\*:?\s*(.*)", text)
        body = inline.group(1) if inline else ""
        if not inline and re.search(r"\bAPPROVE\b", text):
            return False
    else:
        body = match.group(1)
    body = body.strip()
    if not body:
        return False
    first = body.splitlines()[0].strip().lower()
    return not (first.startswith("none") or first.startswith("no ") or first.startswith("nothing") or "no blocking" in first)


def section_items(text: str, heading: str) -> int:
    """Count bullet items under a '## <heading>' section; 0 when the section says none."""
    match = re.search(rf"^#{{1,4}}\s*\**{heading}\**:?\s*$(.*?)(?=^#{{1,4}}\s|\Z)", text, re.M | re.S)
    if not match:
        return 0
    body = match.group(1).strip()
    if not body or body.splitlines()[0].strip().lower().startswith(("none", "no ", "nothing")):
        return 0
    return sum(1 for line in body.splitlines() if re.match(r"^\s*(-|\*|\d+\.)\s+", line)) or 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticket")
    parser.add_argument("--spec")
    parser.add_argument("--base")
    parser.add_argument("--head", required=True)
    parser.add_argument("--remote", default="origin")
    parser.add_argument("--head-branch")
    parser.add_argument("--test-pattern", default=DEFAULT_TEST_PATTERN)
    parser.add_argument("--reports", default=".deliver/reports")
    parser.add_argument("--repo", default=".")
    parser.add_argument("--post", action="store_true")
    parser.add_argument("--merged")
    parser.add_argument("--reviewed-head", help="the last head a verdict covered; the delta since it is listed and classified for the closing round")
    args = parser.parse_args()
    repo = Path(args.repo)
    fails = 0

    if args.post:
        if not args.merged:
            sys.exit("--post needs --merged <ref>")
        head, merged = resolve(repo, args.head), resolve(repo, args.merged)
        if not head or not merged:
            print(f"refs: head={head} merged={merged} (unresolved)")
            sys.exit(1)
        diff = git(repo, "diff", "--stat", args.head, args.merged).strip()
        if diff:
            print(f"post-merge: trees DIFFER between {head} and {merged}:\n{diff}")
            sys.exit(1)
        print(f"post-merge: identical trees {head} == {merged}")
        sys.exit(0)

    for name in ("ticket", "spec", "base"):
        if not getattr(args, name):
            sys.exit(f"--{name} is required for the pre-merge checks")

    # 1. fetch and resolve
    if args.head_branch:
        subprocess.run(["git", "-C", str(repo), "fetch", "-q", args.remote,
                        f"+refs/heads/{args.head_branch}:refs/remotes/{args.remote}/{args.head_branch}"], check=False)
    base, head = resolve(repo, args.base), resolve(repo, args.head)
    if not base or not head:
        print(f"refs: base={base} head={head} (unresolved)")
        sys.exit(1)
    merge_base = git(repo, "merge-base", args.base, args.head).strip()[:8]
    moved = merge_base != base
    print(f"refs: base {base} head {head} merge-base {merge_base}" + (" (the base has moved since the branch point; the diff below is against the merge-base, and the host merges three-way)" if moved else ""))

    # 2. changed files against the spec (three-dot: the PR's own changes since it branched)
    changed = [line for line in git(repo, "diff", "--name-only", f"{args.base}...{args.head}").split("\n") if line]
    status = git(repo, "diff", "--name-status", f"{args.base}...{args.head}").strip()
    print(f"changed files ({len(changed)}):\n{status}")
    spec_text = Path(args.spec).read_text(encoding="utf-8")
    named = set(re.findall(r"`([^`\s]+)`", spec_text))
    # a spec may name a file by full path, by basename, or by a trailing sub-path (`PreviewProof/x.test.tsx`)
    def matches(path: str, name: str) -> bool:
        if path == name or path.endswith('/' + name) or Path(path).name == name:
            return True
        # a spec may name a generated file with a placeholder: `<timestamp>_Name.cs`, `*_Name.cs`, `{n}_Name.cs`.
        # The basename must keep at least six literal characters in its stem, or the token is prose
        # (`<pre>`, `<workspace>`, `*.test.tsx`) and names no file: such a token once matched every path.
        wildcard = r"<[^>]+>|\{[^}]+\}|\*"
        if not re.search(wildcard, name):
            return False
        stem = re.sub(r"\.[A-Za-z0-9]+$", "", name.rsplit("/", 1)[-1])
        literal = re.sub(r"[^A-Za-z0-9]", "", re.sub(wildcard, "", stem))
        if len(literal) < 6:
            return False
        pattern = ".*".join(re.escape(part) for part in re.split(wildcard, name))
        return re.fullmatch(pattern, path) is not None or re.fullmatch(pattern, Path(path).name) is not None or re.fullmatch(".*/" + pattern, path) is not None
    unnamed = [f for f in changed if not any(matches(f, n) for n in named)]
    if unnamed:
        fails += 1
        print("NOT NAMED IN THE SPEC: " + ", ".join(unnamed))
    else:
        print("every changed file is named in the spec")

    # 3. production touches
    pattern = re.compile(args.test_pattern)
    production = [f for f in changed if not pattern.search(f)]
    print("production files touched: " + (", ".join(production) if production else "(none)"))

    # 4. verdict files
    reports = Path(args.reports)
    for axis in ("spec", "standards"):
        latest = latest_verdict(reports, args.ticket, axis)
        if not latest:
            fails += 1
            print(f"verdict {axis}: MISSING under {reports}")
            continue
        text = latest.read_text(encoding="utf-8")
        if blocking_open(text):
            fails += 1
            print(f"verdict {axis}: {latest.name} has an OPEN Blocking section")
        else:
            should = section_items(text, "Should-fix")
            if should:
                print(f"verdict {axis}: {latest.name} no Blocking, but {should} Should-fix item(s) listed; read the whole file and confirm each is closed on the head before completing")
            else:
                print(f"verdict {axis}: {latest.name} clean")

    # 5. closing-round delta since the last reviewed head
    if args.reviewed_head:
        reviewed = resolve(repo, args.reviewed_head)
        if not reviewed:
            fails += 1
            print(f"reviewed head {args.reviewed_head} does not resolve")
        else:
            delta = [line for line in git(repo, "diff", "--name-only", args.reviewed_head, args.head).split("\n") if line]
            stat = git(repo, "diff", "--numstat", args.reviewed_head, args.head).strip()
            if not delta:
                print(f"closing delta since {reviewed}: none (head already reviewed)")
            else:
                code = [f for f in delta if not pattern.search(f)]
                print(f"closing delta since {reviewed} ({len(delta)} files):\n{stat}")
                print("closing delta: TRIVIAL by pattern (tests, docs, bookkeeping only); read the hunks before merging" if not code
                      else "closing delta: touches non-test files " + ", ".join(code) + "; one confirm reviewer on the affected axis unless the hunks are exactly the edits the verdicts asked for")

    print(f"== failed checks: {fails}")
    sys.exit(fails)


if __name__ == "__main__":
    main()
