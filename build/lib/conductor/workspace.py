import subprocess
import os
import shutil


def run_git(args, cwd):
    return subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)


def is_git_repo(path):
    r = run_git(["rev-parse", "--is-inside-work-tree"], path)
    return r.returncode == 0


def current_head(path):
    r = run_git(["rev-parse", "HEAD"], path)
    return r.stdout.strip() if r.returncode == 0 else None


def is_dirty(path):
    r = run_git(["status", "--porcelain"], path)
    return bool(r.stdout.strip())


def create_worktree(repo, branch, base_commit, worktree_path):
    # ensure branch doesn't exist? create new branch from base_commit
    os.makedirs(os.path.dirname(worktree_path), exist_ok=True)
    r = run_git(["worktree", "add", "-b", branch, worktree_path, base_commit], repo)
    if r.returncode != 0:
        # maybe branch exists; try without -b
        r2 = run_git(["worktree", "add", worktree_path, branch], repo)
        if r2.returncode != 0:
            raise RuntimeError(r.stderr + r2.stderr)
    return worktree_path


def remove_worktree(repo, worktree_path, force=False):
    args = ["worktree", "remove", worktree_path]
    if force:
        args.append("--force")
    r = run_git(args, repo)
    return r.returncode == 0


def merge_branch(repo, branch, into="integration"):
    # checkout integration, merge branch
    run_git(["checkout", into], repo)
    r = run_git(["merge", "--no-ff", branch, "-m", f"integrate {branch}"], repo)
    return r.returncode == 0, r.stdout + r.stderr