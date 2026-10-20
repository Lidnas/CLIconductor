import sys, os, time, subprocess
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from conductor.process import ProcessHandle


def test_spawn_and_cancel():
    # spawn a long-running process
    ph = ProcessHandle(["python", "-c", "import time; time.sleep(60)"], cwd=os.getcwd())
    ph.start()
    assert ph.is_alive()
    time.sleep(0.5)
    ph.cancel(graceful_timeout=2.0)
    time.sleep(0.5)
    assert not ph.is_alive()


def test_output_capture():
    ph = ProcessHandle(["python", "-c", "print('hello'); print('world')"], cwd=os.getcwd())
    ph.start()
    ph.wait(timeout=5)
    lines, seq = ph.snapshot_lines()
    joined = "".join(lines)
    assert "hello" in joined
    assert "world" in joined
    assert seq >= 2