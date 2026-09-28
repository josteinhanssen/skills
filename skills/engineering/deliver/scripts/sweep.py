#!/usr/bin/env python3
"""Remove merged, clean worktrees and their local and remote branches; report the rest.

Usage:
  sweep.py [--path <repo>] --host azure-devops --org <url> --project "<project>" --repo "<repo>" [--ticket <branch>] [--dry-run]
  sweep.py [--path <repo>] --host github [--repo <owner/name>] [--ticket <branch>] [--dry-run]
  sweep.py [--path <repo>] --merged-into <ref> --ticket <branch> [--dry-run]
  sweep.py [--path <repo>] --worktree <path> [--dry-run]

Options:
  --path <repo>           the repository to sweep: its checkout or any of its worktrees (default: the
                          current directory). Exit 1 when it is not inside a git repository, and when
                          --ticket names a branch with no worktree, local branch or remote branch there.
                          --repo is the host's repository name, not a path.
  --keep-branch <name>    never delete (repeatable; integration, batch, prototype branches)
  --keep-path <path>      never remove this worktree (repeatable; active agents, scratch)
  --pattern <regex>       branches considered ticket branches (default: feature/|batch-|batch/|msite-|ticket/)

Host modes (--host; PR-completed, for batch branches). Azure DevOps needs --org, --project and --repo.
When the host CLI gives no readable answer for a branch, the script stops there with exit 1 and
the CLI's message. Rules in order for every non-primary worktree:
  keep if its path is protected, it is detached, its PR is not completed, its tree is dirty,
  or its head differs from the PR's merged source commit;
  otherwise `git worktree remove` (never --force), `git branch -D`, and delete the remote branch.
Then remote ticket branches without a worktree are deleted under the same PR rule, and local
branches whose remote is gone are deleted. Before removing a worktree the script checks that no
other worktree's node_modules symlink resolves into it.

--merged-into mode (for one ticket branch, once its merge into the batch branch is pushed): keep
if the branch's worktree path is protected or missing, its head is not an ancestor of <ref>, or
its tree is dirty; otherwise clear ignored build output, `git worktree remove` (never --force)
and `git branch -D`. Never touches the remote and never calls a host CLI.

--worktree mode (for a detached worktree, such as a reviewer's measurement worktree): keep it if
its path is protected, it is on a branch (sweep that with --ticket), its tree is dirty or another
worktree's node_modules resolves into it; otherwise clear ignored build output and `git worktree
remove` it. Never touches a branch.
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


class HostError(Exception):
    """The host CLI gave no readable answer (not signed in, wrong organisation, network)."""


class Host:
    def pr_state(self, branch: str) -> tuple[str, str | None, str]:
        """(status, pr id, merged source commit); raises HostError when the host can't be read"""
        raise NotImplementedError


def parse_prs(out: str, cmd: list[str]) -> list[dict]:
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        raise HostError(f"`{' '.join(cmd[:3])} ...` answered: {out[:300] or '(nothing)'}") from None


class AzureDevOps(Host):
    def __init__(self, org: str, project: str, repo: str):
        self.org, self.project, self.repo = org, project, repo

    def pr_state(self, branch: str):
        cmd = [
            "az", "repos", "pr", "list", "--organization", self.org, "--project", self.project,
            "--repository", self.repo, "--source-branch", branch, "--status", "all", "-o", "json",
        ]
        rc, out = sh(cmd)
        prs = parse_prs(out, cmd)
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
        prs = parse_prs(out, cmd)
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


def is_ancestor(repo: str, commit: str, ref: str) -> bool:
    rc, _ = sh(["git", "merge-base", "--is-ancestor", commit, ref], cwd=repo)
    return rc == 0


def branch_exists(repo: str, branch: str) -> bool:
    local = sh(["git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}"], cwd=repo)[0] == 0
    rc, remote = sh(["git", "ls-remote", "--heads", "origin", branch], cwd=repo)
    return local or (rc == 0 and bool(remote))


def sweep_worktree(args: argparse.Namespace, repo: str, entries: list[dict], keep_paths: set[str], run) -> int:
    target = os.path.realpath(args.worktree)
    entry = next((e for e in entries if os.path.realpath(e["path"]) == target), None)
    if entry is None:
        print(f"no worktree at {args.worktree} in {repo}")
        return 0
    reason = None
    if target in keep_paths or target == os.path.realpath(entries[0]["path"]):
        reason = "protected path"
    elif entry.get("branch") != "(detached)":
        reason = f"on branch {entry.get('branch')}; sweep it with --ticket"
    else:
        rc, dirty = sh("git status --porcelain | wc -l", cwd=target)
        if dirty.strip() != "0":
            reason = f"dirty ({dirty.strip()} entries)"
        elif symlink_targets_into(entries, target):
            reason = f"node_modules symlink target of {symlink_targets_into(entries, target)}"
    if reason:
        print(f"KEEP    {entry['path']} — {reason}")
        return 0
    run(["git", "clean", "-fdXq"], cwd=target)
    rc, out = run(["git", "worktree", "remove", target], cwd=repo)
    if rc != 0:
        print(f"KEEP    {entry['path']} — remove failed: {out[:100]}")
        return 0
    print(f"REMOVED {entry['path']} [detached]")
    return 0


def sweep_merged_into(args: argparse.Namespace, repo: str, entries: list[dict], primary: str,
                       keep_branches: set[str], keep_paths: set[str], run) -> None:
    removed, kept = [], []
    for e in entries:
        path = os.path.realpath(e["path"])
        branch = e.get("branch", "?")
        if path == primary or branch != args.ticket:
            continue
        reason = None
        if path in keep_paths:
            reason = "protected path"
        elif branch == "(detached)":
            reason = "detached"
        elif branch in keep_branches:
            reason = "protected branch"
        else:
            rc, head = sh(["git", "rev-parse", "HEAD"], cwd=path)
            if rc != 0 or not is_ancestor(repo, head, args.merged_into):
                reason = f"head {head[:8]} is not an ancestor of {args.merged_into}"
            else:
                rc, dirty = sh("git status --porcelain | wc -l", cwd=path)
                if dirty.strip() != "0":
                    reason = f"dirty ({dirty.strip()} entries)"
                elif symlink_targets_into(entries, path):
                    reason = f"node_modules symlink target of {symlink_targets_into(entries, path)}"
        if reason:
            kept.append((e["path"], branch, reason))
            print(f"KEEP    {e['path']} [{branch}] — {reason}")
            continue
        run(["git", "clean", "-fdXq"], cwd=path)
        rc, out = run(["git", "worktree", "remove", path], cwd=repo)
        if rc != 0:
            kept.append((e["path"], branch, f"remove failed: {out[:80]}"))
            print(f"KEEP    {e['path']} — remove failed: {out[:100]}")
            continue
        run(["git", "branch", "-D", branch], cwd=repo)
        removed.append((e["path"], branch))
        print(f"REMOVED {e['path']} [{branch}]")
    if not removed and not kept:
        print(f"no worktree found for ticket branch {args.ticket} in {repo}")
    print(f"\nSUMMARY: {repo}: removed {len(removed)} worktree(s) merged into {args.merged_into}, kept {len(kept)}")
    for k in kept:
        print("  kept:", k)


def pr_state_or_exit(host: Host, branch: str) -> tuple[str, str | None, str]:
    try:
        return host.pr_state(branch)
    except HostError as err:
        sys.exit(f"could not read the PR for {branch} from the host: {err}\nStopped there; check the host arguments and the CLI's sign-in")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--path", default=os.getcwd(), help="the repository to sweep (default: the current directory)")
    ap.add_argument("--worktree", help="remove this one detached worktree when it is clean; touches no branch")
    ap.add_argument("--host", choices=["azure-devops", "github"], help="required unless --merged-into or --worktree is given")
    ap.add_argument("--merged-into", help="ref a ticket branch's head must be an ancestor of; used with --ticket to remove one merged ticket's worktree and local branch without the remote or a host CLI")
    ap.add_argument("--org", default=os.environ.get("AZURE_DEVOPS_ORG", ""))
    ap.add_argument("--project")
    ap.add_argument("--repo")
    ap.add_argument("--ticket", help="only this branch")
    ap.add_argument("--keep-branch", action="append", default=[])
    ap.add_argument("--keep-path", action="append", default=[])
    ap.add_argument("--pattern", default=r"^(feature/|batch-|batch/|msite-|ticket/)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.merged_into and not args.host and not args.worktree:
        ap.error("--host is required unless --merged-into or --worktree is given")
    if args.merged_into and not args.ticket:
        ap.error("--merged-into requires --ticket")
    if args.host == "azure-devops" and not (args.org and args.project and args.repo):
        ap.error("--host azure-devops needs --org, --project and --repo; the profile's Sweep line has them")

    rc, top = sh(["git", "rev-parse", "--show-toplevel"], cwd=args.path)
    if rc != 0:
        sys.exit(f"{args.path} is not inside a git repository; pass --path <repository checkout or worktree>")
    repo = top
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

    if args.worktree:
        sys.exit(sweep_worktree(args, repo, entries, keep_paths, run))

    if args.ticket and not any(e.get("branch") == args.ticket for e in entries) and not branch_exists(repo, args.ticket):
        sys.exit(f"branch {args.ticket} has no worktree, local branch or remote branch in {repo}; check --path and the branch name")

    if args.merged_into:
        sweep_merged_into(args, repo, entries, primary, keep_branches, keep_paths, run)
        sh(["git", "worktree", "prune"], cwd=repo)
        return

    host = AzureDevOps(args.org, args.project, args.repo) if args.host == "azure-devops" else GitHub(args.repo)
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
            status, pr, merged = pr_state_or_exit(host, branch)
            rc, dirty = sh("git status --porcelain | wc -l", cwd=path)
            rc, head = sh(["git", "rev-parse", "HEAD"], cwd=path)
            rc, remote = sh(["git", "rev-parse", "-q", "--verify", f"origin/{branch}"], cwd=path)
            remote = remote if rc == 0 else head  # a pruned tracking ref: the host deleted the branch
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
        # Ignored build output (bin/, obj/, .next/) survives the tracked-file deletion and
        # makes `git worktree remove` fail with "Directory not empty" after git has already
        # dropped the worktree entry, leaving an orphan checkout. Clearing ignored files
        # first (-X: ignored only, never untracked work) is safe on a tree measured clean.
        run(["git", "clean", "-fdXq"], cwd=path)
        rc, out = run(["git", "worktree", "remove", path], cwd=repo)
        if rc != 0:
            kept.append((e["path"], branch, f"remove failed: {out[:80]}"))
            print(f"KEEP    {e['path']} — remove failed: {out[:100]}")
            continue
        run(["git", "branch", "-D", branch], cwd=repo)
        removed.append((e["path"], branch))
        print(f"REMOVED {e['path']} [{branch}]")
        rc, live_ref = sh(["git", "ls-remote", "--heads", "origin", branch], cwd=repo)
        if rc == 0 and not live_ref:
            # The host deleted the branch when the PR completed; only the tracking ref is left.
            run(["git", "branch", "-dr", f"origin/{branch}"], cwd=repo)
            deleted_remote.append((branch, "already deleted on origin"))
            continue
        rc, out = run(["git", "push", "origin", "--delete", branch], cwd=repo)
        (deleted_remote if rc == 0 else kept_remote).append((branch, out[:80]))

    if not args.ticket:
        rc, out = sh("git ls-remote --heads origin | awk '{print $2}' | sed 's#refs/heads/##'", cwd=repo)
        live = {e.get("branch") for e in worktrees(repo)}
        for branch in out.split():
            if not pattern.match(branch) or branch in live or branch in keep_branches:
                continue
            status, pr, merged = pr_state_or_exit(host, branch)
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
    print(f"\nSUMMARY: {repo}: removed {len(removed)} worktrees, deleted {len(deleted_remote)} remote branches; kept {len(kept)} worktrees, {len(kept_remote)} remote branches kept or failed")
    for k in kept:
        print("  kept worktree:", k)
    for k in kept_remote:
        print("  kept remote:", k)


if __name__ == "__main__":
    main()
