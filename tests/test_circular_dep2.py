import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.models import Run
from conductor.task_engine import TaskEngine


def test_create_task_cycle_rejected():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="x")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    engine.create_task(objective="a", role="impl", task_id="a")
    engine.create_task(objective="b", role="impl", task_id="b", dependencies=["a"])
    # now create c depending on b, then make a depend on c -> cycle; but a already exists.
    # Create a new task d that depends on b, and b depends on a; adding dependency c->a where a->? 
    # Simulate: create task c with deps [b], then manually set a deps to [c] and try create another
    engine.create_task(objective="c", role="impl", task_id="c", dependencies=["b"])
    # Now attempt to create task that creates cycle: dep on c while c chain leads back?
    # Easiest: create task e depending on c, then we can't easily. Instead test engine rejects when
    # we re-add a task whose deps form cycle.
    try:
        # force a cycle by creating a task 'a2' that depends on c, and modify c to depend on a2
        engine.tasks["c"].dependencies = ["a2"]
        engine.create_task(objective="a2", role="impl", task_id="a2", dependencies=["c"])
        # if no exception, fail
        assert False, "cycle not rejected"
    except ValueError as e:
        assert "circular" in str(e).lower() or "cycle" in str(e).lower()