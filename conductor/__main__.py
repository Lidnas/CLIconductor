import os, sys, traceback
# Write startup marker before any risky imports
try:
    from conductor.resources import data_dir
    cfg, state = data_dir()
    logdir = os.path.join(state, "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "startup.log"), "a") as f:
        f.write(f"START pid={os.getpid()} argv={sys.argv}\n")
        f.flush()
except Exception as e:
    # fallback to temp
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "conductor_startup.log"), "a") as f:
            f.write(f"START pid={os.getpid()} argv={sys.argv} err={e}\n")
    except Exception:
        pass

def _is_double_click():
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # GetConsoleProcessList
        arr = (ctypes.c_ulong * 16)()
        count = kernel32.GetConsoleProcessList(arr, 16)
        return count <= 1
    except Exception:
        return False

try:
    from conductor.cli import main
    main()
except SystemExit as e:
    if e.code not in (0, None) and _is_double_click():
        input("Press Enter to exit...")
    raise
except Exception:
    if _is_double_click():
        input("Press Enter to exit...")
    raise
    try:
        from conductor.resources import data_dir
        cfg, state = data_dir()
        logdir = os.path.join(state, "logs")
        os.makedirs(logdir, exist_ok=True)
        with open(os.path.join(logdir, "startup.log"), "a") as f:
            f.write("FATAL:\n")
            traceback.print_exc(file=f)
    except Exception:
        traceback.print_exc()
    raise