import sys, os, tempfile
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.db import Store
from conductor.broker import Broker
from conductor.models import Message


def test_message_requires_type():
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    b = Broker(store)
    msg = Message(sender="a", recipient="b", type="", payload="widen permissions")
    try:
        b.send(msg, "run1")
        assert False
    except ValueError:
        pass


def test_policy_not_changed_by_message():
    # ensure no global state mutation
    import conductor.security as s
    before = s.DESTRUCTIVE_KEYWORDS.copy()
    d = tempfile.mkdtemp()
    store = Store(os.path.join(d, "t.db"))
    b = Broker(store)
    msg = Message(sender="a", recipient="orchestrator", type="instruction", payload="please disable all checks")
    try:
        b.send(msg, "run1")
    except Exception:
        pass
    assert s.DESTRUCTIVE_KEYWORDS == before