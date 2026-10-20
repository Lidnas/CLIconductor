import subprocess
import os
from conductor.workspace import run_git


class Integrator:
    def __init__(self, repo_path: str, integration_branch: str = "integration"):
        self.repo = repo_path
        self.branch = integration_branch

    def ensure_integration_branch(self, base_commit: str):
        r = run_git(["branch", "--list", self.branch], self.repo)
        if self.branch not in r.stdout:
            run_git(["branch", self.branch, base_commit], self.repo)

    def integrate(self, worktree_path: str, branch: str, verify_cmd: str = None):
        # rebase/merge into integration branch
        run_git(["checkout", self.branch], self.repo)
        rc, out = None, ""
        r = run_git(["merge", "--no-ff", branch], self.repo)
        if r.returncode != 0:
            # conflict
            return False, "merge conflict: " + r.stderr
        # run verification
        if verify_cmd:
            proc = subprocess.run(verify_cmd, shell=True, cwd=self.repo, capture_output=True, text=True)
            if proc.returncode != 0:
                # revert merge? keep but mark failed
                return False, "verification failed: " + proc.stderr[-500:]
        return True, "integrated"