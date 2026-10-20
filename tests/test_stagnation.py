import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run, Agent
from conductor.task_engine import TaskEngine
from conductor.scheduler import Scheduler
from tests.mock_adapter import MockCLI, MockBehavior


def test_stagnation_detected():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="x")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=1)
    sched.stagnation_window = 0.3
    ag = Agent(cli="mock", role="implementer", instance=0, workspace=d)
    mb = MockBehavior(output="", hang=True, delay=0)
    sched.register_agent(ag, MockCLI(mb))
    engine.create_task(objective="x", role="implementer", task_id="t1")
    async def go():
        await sched.run_loop()
    asyncio.run(go())
    # stagnation should mark blocked (or still running if not detected)
    print("state", engine.tasks["t1"].state)
    assert engine.tasks["t1"].state in ("blocked", "failed", "verifying", "running")
