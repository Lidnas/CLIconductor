import os

__version__ = "0.1.0"

def build_info():
    # build commit/date can be injected via env at build time
    commit = os.environ.get("BUILD_COMMIT", "dev")
    date = os.environ.get("BUILD_DATE", "unknown")
    return __version__, commit, date