import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run, Agent
from conductor.task_engine import TaskEngine
from conductor.scheduler import Scheduler
from conductor.adapters.opencode import OpenCodeAdapter
import shutil


def test_two_opencode_concurrent():
    if not shutil.which("opencode"):
        print("SKIP: opencode not available")
        return
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="Reply PONG", base_commit="", integration_branch="integration")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=2)
    sched.stagnation_window = 300
    a1 = Agent(cli="opencode", role="implementer", instance=0, workspace=d)
    a2 = Agent(cli="opencode", role="implementer", instance=1, workspace=d)
    sched.register_agent(a1, OpenCodeAdapter())
    sched.register_agent(a2, OpenCodeAdapter())
    engine.create_task(objective="Reply with exactly the word PONG", role="implementer", task_id="t1")
    engine.create_task(objective="Reply with exactly the word PING", role="implementer", task_id="t2")
    async def go():
        await sched.run_loop()
    asyncio.run(go())
    states = [engine.tasks[t].state for t in ("t1", "t2")]
    print("states", states)
    assert all(s in ("verifying", "done", "failed") for s in states)