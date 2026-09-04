#!/usr/bin/env python3
"""Remove merged, clean worktrees and their local and remote branches; report the rest.

Usage (from the repository root):
  sweep.py --host azure-devops --project "<project>" --repo "<repo>" [--org <url>] [--ticket <branch>] [--dry-run]
  sweep.py --host github [--repo <owner/name>] [--ticket <branch>] [--dry-run]

Options:
  --keep-branch <name>    never delete (repeatable; integration, batch, prototype branches)
  --keep-path <path>      never remove this worktree (repeatable; active agents, scratch)
  --pattern <regex>       branches considered ticket branches (default: feature/|batch-|msite-|ticket/)

Rules, in order, for every non-primary worktree:
  keep if its path is protected, it is detached, its PR is not completed, its tree is dirty,
  or its head differs from the PR's merged source commit;
  otherwise `git worktree remove` (never --force), `git branch -D`, and delete the remote branch.
Then remote ticket branches without a worktree are deleted under the same PR rule, and local
branches whose remote is gone are deleted. Before removing a worktree the script checks that no
other worktree's node_modules symlink resolves into it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path


def sh(cmd: list[str] | str, cwd: str | None = None) -> tuple[int, str]:
    shell = isinstance(cmd, str)
    proc = subprocess.run(cmd, shell=shell, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, (proc.stdout + proc.stderr).strip()


class Host:
    def pr_state(self, branch: str) -> tuple[str, str | None, str]:
        """(status, pr id, merged source commit)"""
        raise NotImplementedError


class AzureDevOps(Host):
    def __init__(self, org: str, project: str, repo: str):
        self.org, self.project, self.repo = org, project, repo

    def pr_state(self, branch: str):
        rc, out = sh([
            "az", "repos", "pr", "list", "--organization", self.org, "--project", self.project,
            "--repository", self.repo, "--source-branch", branch, "--status", "all", "-o", "json",
        ])
        try:
            prs = json.loads(out)
        except json.JSONDecodeError:
            return ("?", None, "")
        if not prs:
            return ("no-pr", None, "")
        prs.sort(key=lambda p: p["pullRequestId"])
        p = prs[-1]
        return (p["status"], str(p["pullRequestId"]), (p.get("lastMergeSourceCommit") or {}).get("commitId", ""))


class GitHub(Host):
    def __init__(self, repo: str | None):
        self.repo = repo

    def pr_state(self, branch: str):
        cmd = ["gh", "pr", "list", "--head", branch, "--state", "all", "--json", "number,state,mergeCommit,headRefOid", "--limit", "5"]
        if self.repo:
            cmd += ["--repo", self.repo]
        rc, out = sh(cmd)
        try:
            prs = json.loads(out)
        except json.JSONDecodeError:
            return ("?", None, "")
        if not prs:
            return ("no-pr", None, "")
        prs.sort(key=lambda p: p["number"])
        p = prs[-1]
        status = "completed" if p.get("state") == "MERGED" else p.get("state", "?").lower()
        return (status, str(p["number"]), p.get("headRefOid", ""))


def worktrees(repo: str) -> list[dict]:
    rc, out = sh(["git", "worktree", "list", "--porcelain"], cwd=repo)
    entries, cur = [], {}
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": line[9:]}
        elif line.startswith("branch "):
            cur["branch"] = line[7:].replace("refs/heads/", "")
        elif line.startswith("detached"):
            cur["branch"] = "(detached)"
        elif line == "" and cur:
            entries.append(cur)
            cur = {}
    return entries


def symlink_targets_into(entries: list[dict], target: str) -> list[str]:
    hits = []
    target = os.path.realpath(target)
    for e in entries:
        link = Path(e["path"]) / "node_modules"
        if link.is_symlink():
            resolved = os.path.realpath(link)
            if resolved.startswith(target + os.sep) or resolved == target:
                hits.append(e["path"])
    return hits


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", choices=["azure-devops", "github"], required=True)
    ap.add_argument("--org", default=os.environ.get("AZURE_DEVOPS_ORG", ""))
    ap.add_argument("--project")
    ap.add_argument("--repo")
    ap.add_argument("--ticket", help="only this branch")
    ap.add_argument("--keep-branch", action="append", default=[])
    ap.add_argument("--keep-path", action="append", default=[])
    ap.add_argument("--pattern", default=r"^(feature/|batch-|msite-|ticket/)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    repo = os.getcwd()
    host = AzureDevOps(args.org, args.project, args.repo) if args.host == "azure-devops" else GitHub(args.repo)
    keep_branches = set(args.keep_branch) | {"main", "master", "dev"}
    keep_paths = {os.path.realpath(p) for p in args.keep_path}
    pattern = re.compile(args.pattern)

    def run(cmd, cwd=None):
        if args.dry_run:
            print("   would run:", cmd if isinstance(cmd, str) else " ".join(cmd))
            return 0, ""
        return sh(cmd, cwd)

    sh(["git", "worktree", "prune"], cwd=repo)
    entries = worktrees(repo)
    primary = os.path.realpath(entries[0]["path"]) if entries else repo
    removed, kept, deleted_remote, kept_remote = [], [], [], []

    for e in entries:
        path = os.path.realpath(e["path"])
        branch = e.get("branch", "?")
        if path == primary:
            continue
        if args.ticket and branch != args.ticket:
            continue
        reason = None
        if path in keep_paths:
            reason = "protected path"
        elif branch == "(detached)":
            reason = "detached"
        elif branch in keep_branches:
            reason = "protected branch"
        else:
            status, pr, merged = host.pr_state(branch)
            rc, dirty = sh("git status --porcelain | wc -l", cwd=path)
            rc, head = sh(["git", "rev-parse", "HEAD"], cwd=path)
            rc, remote = sh(["git", "rev-parse", "-q", "--verify", f"origin/{branch}"], cwd=path)
            if status != "completed":
                reason = f"PR {status}"
            elif dirty.strip() != "0":
                reason = f"dirty ({dirty.strip()} entries)"
            elif not (head == remote == merged):
                reason = "head differs from the merged commit"
            elif symlink_targets_into(entries, path):
                reason = f"node_modules symlink target of {symlink_targets_into(entries, path)}"
        if reason:
            kept.append((e["path"], branch, reason))
            print(f"KEEP    {e['path']} [{branch}] — {reason}")
            continue
        rc, out = run(["git", "worktree", "remove", path], cwd=repo)
        if rc != 0:
            kept.append((e["path"], branch, f"remove failed: {out[:80]}"))
            print(f"KEEP    {e['path']} — remove failed: {out[:100]}")
            continue
        run(["git", "branch", "-D", branch], cwd=repo)
        removed.append((e["path"], branch))
        print(f"REMOVED {e['path']} [{branch}]")
        rc, out = run(["git", "push", "origin", "--delete", branch], cwd=repo)
        (deleted_remote if rc == 0 else kept_remote).append((branch, out[:80]))

    if not args.ticket:
        rc, out = sh("git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##'", cwd=repo)
        live = {e.get("branch") for e in worktrees(repo)}
        for branch in out.split():
            if not pattern.match(branch) or branch in live or branch in keep_branches:
                continue
            status, pr, merged = host.pr_state(branch)
            rc, remote_head = sh(["git", "rev-parse", f"origin/{branch}"], cwd=repo)
            if status == "completed" and merged and remote_head == merged:
                rc, out2 = run(["git", "push", "origin", "--delete", branch], cwd=repo)
                (deleted_remote if rc == 0 else kept_remote).append((branch, out2[:80]))
                print(f"remote-only branch {'deleted' if rc == 0 else 'KEPT (delete failed)'}: {branch}")
            else:
                kept_remote.append((branch, f"{status} head={remote_head[:8]} merged={merged[:8]}"))
                print(f"remote-only branch KEPT: {branch} — {status}")
        rc, local = sh("git branch --format='%(refname:short)'", cwd=repo)
        for branch in local.split():
            if not pattern.match(branch) or branch in keep_branches or branch in live:
                continue
            rc, _ = sh(["git", "rev-parse", "--verify", "-q", f"origin/{branch}"], cwd=repo)
            if rc != 0:
                run(["git", "branch", "-D", branch], cwd=repo)
                print(f"local branch deleted (remote gone): {branch}")

    sh(["git", "worktree", "prune"], cwd=repo)
    print(f"\nSUMMARY: removed {len(removed)} worktrees, deleted {len(deleted_remote)} remote branches; kept {len(kept)} worktrees, {len(kept_remote)} remote branches kept or failed")
    for k in kept:
        print("  kept worktree:", k)
    for k in kept_remote:
        print("  kept remote:", k)


if __name__ == "__main__":
    main()
