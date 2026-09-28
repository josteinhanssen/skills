#!/usr/bin/env python3
"""Content verification of merges, host-agnostic.

Usage:
  verify-merge.py --repo <path> --delta <from-ref> <to-ref> [--sizes] [--test-pattern <regex>] [--doc-pattern <regex>] [--generated-pattern <regex>]
  verify-merge.py --repo <path> --reviewed <ref> --merged <ref>

--delta: lists the files changed between the two refs, added/removed line counts, each
classified doc / generated / test / production, and a totals line. Exit 0 unless a ref fails to
resolve. With --sizes it prints only the changed lines (added plus removed) per class, on one line:
`production <n> test <n> doc <n> generated <n>`. Generated files are EF migration designers and
snapshots, lock files and *.g.cs; they count toward no size bar.

--reviewed/--merged: exit 0 when the merged ref's tree equals the reviewed ref's tree, or when
the merged ref is the clean merge of the reviewed ref onto a target that moved (the target's tip
just before the merge is the merged commit's first parent); otherwise exit 1 and list the
differing paths. Content verification of the merged head can then rely on the checks already run
against the reviewed head.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

DEFAULT_TEST_PATTERN = r"(\.test\.[cm]?[jt]sx?$|\.spec\.[cm]?[jt]sx?$|(^|/)tests?/|(^|/)__tests__/|(^|/)[^/]+\.[A-Za-z]*Tests?/|[A-Za-z]Tests?\.cs$|budget\.json$|_test\.go$|_test\.py$|(^|/)test_[^/]+\.py$)"
DEFAULT_DOC_PATTERN = r"(\.md$|\.mdx$|(^|/)docs/|(^|/)README(\.[^/]+)?$)"
DEFAULT_GENERATED_PATTERN = r"(\.Designer\.cs$|ModelSnapshot\.cs$|\.g\.cs$|\.generated\.[^/]+$|(^|/)package-lock\.json$|(^|/)packages\.lock\.json$)"


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(repo), *args], text=True)


def resolve(repo: Path, ref: str) -> str | None:
    try:
        return git(repo, "rev-parse", "--short", "--verify", f"{ref}^{{commit}}").strip()
    except subprocess.CalledProcessError:
        return None


def cmd_delta(repo: Path, from_ref: str, to_ref: str, patterns: dict[str, str], sizes: bool) -> int:
    from_sha, to_sha = resolve(repo, from_ref), resolve(repo, to_ref)
    if not from_sha or not to_sha:
        print(f"refs: from={from_sha} to={to_sha} (unresolved)")
        return 1
    # First match wins, in this order: a designer file under docs/ is still a doc.
    classes = [(kind, re.compile(patterns[kind])) for kind in ("doc", "generated", "test")]
    numstat = git(repo, "diff", "--numstat", from_ref, to_ref).strip()
    counts = {"production": 0, "test": 0, "doc": 0, "generated": 0}
    changed = dict.fromkeys(counts, 0)
    total_added = total_removed = 0
    lines = []
    for line in numstat.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, path = parts
        kind = next((k for k, pattern in classes if pattern.search(path)), "production")
        counts[kind] += 1
        a, r = (0 if added == "-" else int(added)), (0 if removed == "-" else int(removed))
        changed[kind] += a + r
        total_added += a
        total_removed += r
        lines.append(f"+{added:<5} -{removed:<5} {kind:<10} {path}")
    if sizes:
        print(" ".join(f"{kind} {n}" for kind, n in changed.items()))
        return 0
    print(f"delta {from_sha}..{to_sha} ({len(lines)} files)")
    for line in lines:
        print(line)
    print(
        f"== totals: files {len(lines)} (test {counts['test']}, doc {counts['doc']}, "
        f"generated {counts['generated']}, production {counts['production']})  +{total_added} -{total_removed}"
    )
    return 0


def cmd_compare(repo: Path, reviewed_ref: str, merged_ref: str) -> int:
    reviewed, merged = resolve(repo, reviewed_ref), resolve(repo, merged_ref)
    if not reviewed or not merged:
        print(f"refs: reviewed={reviewed} merged={merged} (unresolved)")
        return 1
    diff = git(repo, "diff", "--name-status", reviewed_ref, merged_ref).strip()
    if not diff:
        print(f"trees identical: {reviewed} == {merged}")
        return 0
    # The target may have moved between the review and the completion (another PR landed first).
    # Then the merged tree is not the reviewed ref's tree but the clean three-way merge of it onto
    # the target's tip just before the merge, which is the merged commit's first parent. Recompute
    # that merge and compare trees; only a difference there is a defect.
    parent = git(repo, "rev-parse", "--verify", "-q", f"{merged_ref}^1").strip()
    expected = git(repo, "merge-tree", "--write-tree", parent, reviewed_ref).strip().splitlines()
    expected_tree = expected[0] if expected else ""
    if expected_tree and len(expected) == 1:
        residue = git(repo, "diff", "--name-status", expected_tree, f"{merged_ref}^{{tree}}").strip()
        if not residue:
            print(
                f"the target moved to {parent[:8]} before completion; {merged} is the clean merge "
                f"of {reviewed} onto it (merge-tree {expected_tree[:8]}, identical)"
            )
            return 0
        print(f"trees DIFFER between the clean merge of {reviewed} onto {parent[:8]} and {merged}:\n{residue}")
        return 1
    print(f"trees DIFFER between {reviewed} and {merged}:\n{diff}")
    return 1


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--delta", nargs=2, metavar=("FROM", "TO"))
    parser.add_argument("--reviewed")
    parser.add_argument("--merged")
    parser.add_argument("--test-pattern", default=DEFAULT_TEST_PATTERN)
    parser.add_argument("--doc-pattern", default=DEFAULT_DOC_PATTERN)
    parser.add_argument("--generated-pattern", default=DEFAULT_GENERATED_PATTERN)
    parser.add_argument("--sizes", action="store_true", help="with --delta: one line of changed lines per class")
    args = parser.parse_args()
    repo = Path(args.repo)

    if args.delta:
        patterns = {"test": args.test_pattern, "doc": args.doc_pattern, "generated": args.generated_pattern}
        sys.exit(cmd_delta(repo, args.delta[0], args.delta[1], patterns, args.sizes))
    if args.reviewed and args.merged:
        sys.exit(cmd_compare(repo, args.reviewed, args.merged))
    sys.exit("pass --delta <from> <to>, or --reviewed <ref> --merged <ref>")


if __name__ == "__main__":
    main()
