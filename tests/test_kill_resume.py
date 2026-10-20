import sys, os, tempfile, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run
from conductor.task_engine import TaskEngine


def test_lease_expiry_recovery():
    d = tempfile.mkdtemp()
    db = os.path.join(d, "t.db")
    store = Store(db)
    run = Run(objective="x")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    t = engine.create_task(objective="x", role="impl", task_id="t1")
    engine.transition("t1", "ready")
    lease = engine.lease("t1", "agentA", ttl=0.1)
    # simulate crash: expire
    time.sleep(0.2)
    engine.expire_leases()
    assert engine.tasks["t1"].state == "ready"
    # reload from store (new engine)
    engine2 = TaskEngine(store, run.run_id)
    engine2.load()
    assert engine2.tasks["t1"].state == "ready"