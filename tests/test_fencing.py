import sys, os, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run
from conductor.task_engine import TaskEngine, StaleLeaseError


def test_fencing_token_rejects_stale():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="x")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    t = engine.create_task(objective="x", role="impl")
    engine.transition(t.task_id, "ready")
    lease1 = engine.lease(t.task_id, "agentA")
    ft1 = lease1.fencing_token
    # expire and re-lease
    engine.tasks[t.task_id].state = "ready"
    engine.store.save_task(engine.tasks[t.task_id], run.run_id)
    lease2 = engine.lease(t.task_id, "agentB")
    ft2 = lease2.fencing_token
    assert ft2 != ft1
    # stale release with old token should raise
    try:
        engine.release_lease(t.task_id, ft1)
        assert False, "should raise"
    except StaleLeaseError:
        pass
    # new token works
    engine.release_lease(t.task_id, ft2, result="ok", success=True)