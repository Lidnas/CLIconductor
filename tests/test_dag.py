import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.dag import detect_cycle, topological_order


def test_cycle_detection():
    tasks = {"a": ["b"], "b": ["a"]}
    is_cyc, cycle = detect_cycle(tasks)
    assert is_cyc is True
    assert cycle is not None


def test_no_cycle():
    tasks = {"a": [], "b": ["a"], "c": ["b"]}
    is_cyc, cycle = detect_cycle(tasks)
    assert is_cyc is False


def test_topo_order():
    tasks = {"a": [], "b": ["a"], "c": ["b"]}
    order = topological_order(tasks)
    assert order.index("a") < order.index("b") < order.index("c")