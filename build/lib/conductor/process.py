import os
import sys
import time
import signal
import subprocess
import threading
import platform
from typing import Callable, Optional, List


IS_WIN = platform.system() == "Windows"


def _creationflags():
    if IS_WIN:
        # CREATE_NEW_PROCESS_GROUP | CREATE_BREAKAWAY_FROM_JOB maybe
        return subprocess.CREATE_NEW_PROCESS_GROUP
    return 0


class ProcessHandle:
    def __init__(self, cmd, cwd=None, env=None, on_line: Callable[[str, int], None] = None):
        self.cmd = cmd
        self.cwd = cwd
        self.env = env
        self.on_line = on_line
        self.proc = None
        self.seq = 0
        self.lines: List[str] = []
        self._lock = threading.Lock()
        self._reader_thread = None
        self._alive = False
        self.started_at = None
        self.exit_code = None
        self._job = None

    def start(self):
        self.proc = subprocess.Popen(
            self.cmd,
            cwd=self.cwd,
            env=self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=_creationflags() if IS_WIN else 0,
            start_new_session=(not IS_WIN),
        )
        self.started_at = time.time()
        self._alive = True
        if IS_WIN:
            self._assign_job()
        self._reader_thread = threading.Thread(target=self._read, daemon=True)
        self._reader_thread.start()

    def _assign_job(self):
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            self._job = kernel32.CreateJobObjectW(None, None)
            # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
                _fields_ = [("BasicLimitInformation", ctypes.c_byte * 48),  # placeholder
                            ("IoInfo", ctypes.c_byte * 48),
                            ("ProcessMemoryLimit", ctypes.c_size_t),
                            ("JobMemoryLimit", ctypes.c_size_t),
                            ("PeakProcessMemoryUsed", ctypes.c_size_t),
                            ("PeakJobMemoryUsed", ctypes.c_size_t)]
            info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
            # BasicLimitInformation.LimitFlags at offset 0? Simplify: set kill on close via class
            # Use a simpler approach: store job handle; on kill, terminate job.
            kernel32.AssignProcessToJobObject(self._job, self.proc._handle if hasattr(self.proc, "_handle") else self.proc._handle)
        except Exception:
            self._job = None

    def _read(self):
        try:
            for line in self.proc.stdout:
                with self._lock:
                    self.seq += 1
                    s = self.seq
                    self.lines.append(line)
                if self.on_line:
                    try:
                        self.on_line(line, s)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self.proc.wait()
        except Exception:
            pass
        self.exit_code = self.proc.returncode
        self._alive = False

    def is_alive(self):
        return self._alive and self.proc is not None and self.proc.poll() is None

    def cancel(self, graceful_timeout: float = 5.0, force: bool = False):
        if self.proc is None or self.proc.poll() is not None:
            return
        # graceful
        if not force and not IS_WIN:
            try:
                os.killpg(self.proc.pid, signal.SIGTERM)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        elif not force and IS_WIN:
            try:
                self.proc.send_signal(signal.CTRL_BREAK_EVENT)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass
        else:
            self._kill_tree()
            return
        # wait
        try:
            self.proc.wait(timeout=graceful_timeout)
        except subprocess.TimeoutExpired:
            self._kill_tree()

    def _kill_tree(self):
        if self.proc is None:
            return
        if IS_WIN:
            try:
                subprocess.run(["taskkill", "/T", "/F", "/PID", str(self.proc.pid)],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass
            try:
                self.proc.kill()
            except Exception:
                pass
        else:
            try:
                os.killpg(self.proc.pid, signal.SIGKILL)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        try:
            self.proc.wait(timeout=5)
        except Exception:
            pass

    def wait(self, timeout=None):
        if self.proc is None:
            return self.exit_code
        try:
            return self.proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            return None

    def snapshot_lines(self):
        with self._lock:
            return list(self.lines), self.seq