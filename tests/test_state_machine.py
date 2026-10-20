import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.models import TaskState, LEGAL_TRANSITIONS


def test_legal_transitions():
    assert TaskState.DONE in LEGAL_TRANSITIONS[TaskState.VERIFYING]
    assert TaskState.DONE not in LEGAL_TRANSITIONS[TaskState.PENDING]


def test_illegal_transition_blocked():
    # pending -> done illegal
    assert TaskState.DONE not in LEGAL_TRANSITIONS[TaskState.PENDING]