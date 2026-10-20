import sys, os, asyncio, tempfile, hashlib, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run, Agent, Criterion
from conductor.task_engine import TaskEngine
from conductor.scheduler import Scheduler
from conductor.adapters.opencode import OpenCodeAdapter
from conductor.workspace import current_head
from conductor.verifier import Verifier


def file_hash(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_e2e_real():
    if not shutil.which("opencode"):
        print("SKIP")
        return
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "fixtures", "repo1"))
    subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=repo)
    test_file = os.path.join(repo, "test_calc.py")
    before_hash = file_hash(test_file)

    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="Fix add function so tests pass", base_commit=current_head(repo), integration_branch="integration")
    import sys
    run.criteria.append(Criterion(description="tests", verifier=f'"{sys.executable}" -m pytest test_calc.py -q', verifier_type="command"))
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=1)
    a = Agent(cli="opencode", role="implementer", instance=0, workspace=repo)
    sched.register_agent(a, OpenCodeAdapter())
    task = engine.create_task(objective="Fix the add function in calc.py so that add(2,3) returns 5. Only edit calc.py.", role="implementer", task_id="t1")

    # Run agent
    async def go():
        await sched.run_loop()
    asyncio.run(go())

    # mark task done? It's verifying; run verification in repo
    v = Verifier(repo)
    for c in run.criteria:
        v.run_criterion(c, reruns=1)
    print("criterion status", [c.status for c in run.criteria])
    # protect test file: hash unchanged
    after_hash = file_hash(test_file)
    assert before_hash == after_hash, "test file tampered"
    assert any(c.status == "passed" for c in run.criteria), "verification failed"