import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.broker import Broker
from conductor.models import Message


def test_message_persist_and_dedupe():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    b = Broker(store)
    msg = Message(sender="agent1", recipient="agent2", type="finding", payload={"x": 1}, idempotency_key="k1")
    b.send(msg, "run1")
    msgs = store.list_messages(run_id="run1")
    assert len(msgs) == 1
    # duplicate idempotency
    msg2 = Message(sender="agent1", recipient="agent2", type="finding", payload={"x": 1}, idempotency_key="k1")
    try:
        b.send(msg2, "run1")
    except Exception:
        pass
    msgs = store.list_messages(run_id="run1")
    assert len(msgs) == 1


def test_sender_from_token():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    b = Broker(store)
    # register agent in store by saving
    from conductor.models import Agent
    ag = Agent(agent_id="agentA", token="tokA", cli="mock", role="impl")
    store.save_agent(ag, "run1")
    lookup = lambda tok: store.load_agent_by_token(tok)
    msg = Message(sender="spoofed", recipient="agent2", type="finding", payload="hi")
    out = b.send(msg, "run1", sender_token="tokA", agent_lookup=lookup)
    assert out.sender == "agentA"


def test_rate_limit():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    b = Broker(store, rate_limit_per_agent=2, window_sec=60)
    for i in range(2):
        m = Message(sender="a", recipient="b", type="status", payload=i, idempotency_key=f"k{i}")
        b.send(m, "run1")
    try:
        m = Message(sender="a", recipient="b", type="status", payload=99, idempotency_key="k99")
        b.send(m, "run1")
        assert False, "should rate limit"
    except RuntimeError:
        pass