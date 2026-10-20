import sys, os, asyncio, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run, Task, Criterion
from conductor.task_engine import TaskEngine
from conductor.scheduler import Scheduler
from tests.mock_adapter import MockCLI, MockBehavior


def test_false_completion_caught():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="do thing", base_commit="", integration_branch="integration")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=1)
    # mock agent falsely claims completion
    from conductor.models import Agent
    ag = Agent(cli="mock", role="implementer", instance=0, workspace=d)
    mb = MockBehavior(output="done", false_complete=True, delay=0.1)
    sched.register_agent(ag, MockCLI(mb))
    task = engine.create_task(objective="do thing", role="implementer")
    # run scheduler
    async def go():
        await sched.run_loop()
    asyncio.run(go())
    # task should be in verifying (agent completed) not done
    t = engine.tasks[task.task_id]
    assert t.state in ("verifying", "running", "ready", "leased", "blocked"), t.state
    # not done
    assert t.state != "done"
