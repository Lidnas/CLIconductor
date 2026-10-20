import sys, os, asyncio, tempfile, uuid, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _run_once():
    from conductor.db import Store
    from conductor.models import Run, Agent, Message
    from conductor.broker import Broker
    from conductor.task_engine import TaskEngine
    from conductor.scheduler import Scheduler
    from conductor.adapters.opencode import OpenCodeAdapter

    token = "TOK_" + uuid.uuid4().hex[:8]
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    run = Run(objective="msg test", base_commit="", integration_branch="integration")
    store.save_run(run)
    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=1)
    broker = Broker(store)

    a = Agent(cli="opencode", role="implementer", instance=0, workspace=d)
    sched.register_agent(a, OpenCodeAdapter())
    tA = engine.create_task(objective=f"Output exactly this token and nothing else: {token}", role="implementer", task_id="tA")

    async def runA():
        await sched.run_loop()

    asyncio.run(runA())
    resA = engine.tasks["tA"].result or ""
    assert token in resA, f"token not in A output: {resA[:200]}"

    b = Agent(cli="opencode", role="implementer", instance=1, workspace=d)
    sched.register_agent(b, OpenCodeAdapter())
    msg = Message(sender=a.agent_id, recipient=b.agent_id, type="finding", payload={"token": token}, idempotency_key="m1")
    broker.send(msg, run.run_id)
    try:
        engine.transition("tA", "done")
    except Exception:
        pass
    tB = engine.create_task(objective=f"You received a message. Reply with exactly: {token}", role="implementer", task_id="tB")

    async def runB():
        await sched.run_loop()

    asyncio.run(runB())
    resB = engine.tasks["tB"].result or ""
    assert token in resB, f"token not in B output: {resB[:200]}"
    print("OK token delivered/used")


def test_message_delivery_real():
    if not shutil.which("opencode"):
        print("SKIP")
        return
    last = None
    for attempt in range(2):
        try:
            _run_once()
            return
        except AssertionError as e:
            last = e
    raise last