import subprocess
import hashlib
import time
import os
from conductor.models import Criterion


class Verifier:
    def __init__(self, workdir: str):
        self.workdir = workdir

    def run_criterion(self, crit: Criterion, reruns: int = 1) -> Criterion:
        if crit.verifier_type == "human_signoff" or crit.verifier_type == "reviewer_evidence":
            crit.status = "pending_human"
            crit.evidence = {"note": "requires human/reviewer", "confidence": "low"}
            return crit
        if not crit.verifier:
            crit.status = "no_verifier"
            return crit
        results = []
        for i in range(max(1, reruns)):
            try:
                proc = subprocess.run(crit.verifier, shell=True, cwd=self.workdir,
                                     capture_output=True, text=True, timeout=300)
                results.append((proc.returncode, proc.stdout, proc.stderr))
            except Exception as e:
                results.append((-1, "", str(e)))
        # flakiness check
        exits = [r[0] for r in results]
        flaky = len(set(exits)) > 1
        last = results[-1]
        crit.evidence = {
            "command": crit.verifier,
            "exit_code": last[0],
            "stdout_hash": hashlib.sha256(last[1].encode()).hexdigest(),
            "stderr_tail": last[2][-500:],
            "reruns": len(results),
            "exits": exits,
            "flaky": flaky,
            "timestamp": time.time(),
        }
        if last[0] == crit.expected_exit and not flaky:
            crit.status = "passed"
        elif last[0] == crit.expected_exit and flaky:
            crit.status = "passed_flaky"
        else:
            crit.status = "failed"
        return crit

    def run_all(self, criteria: list, reruns: int = 1) -> list:
        return [self.run_criterion(c, reruns) for c in criteria]