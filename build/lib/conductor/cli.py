import argparse
import os
import sys
import json
import time
import asyncio

try:
    from conductor import __version__
except Exception:
    __version__ = "0.1.0"

DB_DEFAULT = os.path.join(os.getcwd(), ".conductor", "conductor.db")


def _store(path=None):
    from conductor.db import Store
    p = path or DB_DEFAULT
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return Store(p)


def cmd_doctor(args):
    import shutil
    print("CLI Conductor doctor")
    print("Python:", sys.version)
    for cli in ["opencode", "gemini", "qwen", "git"]:
        p = shutil.which(cli)
        print(f"  {cli}: {p if p else 'NOT FOUND'}")
    # check opencode auth by listing models
    try:
        import subprocess
        r = subprocess.run("opencode models", shell=True, capture_output=True, text=True, timeout=60)
        print("  opencode models:", "OK" if r.returncode == 0 else "FAIL")
    except Exception as e:
        print("  opencode models: error", e)
    print("DB path:", DB_DEFAULT)
    print("OK")


def cmd_run(args):
    # create a run, launch orchestrator loop with mock+real agents
    asyncio.run(_run_async(args))


async def _run_async(args):
    from conductor.db import Store
    from conductor.models import Run, Criterion, Agent
    from conductor.task_engine import TaskEngine
    from conductor.scheduler import Scheduler
    from conductor.adapters.mock import MockCLI, MockBehavior
    from conductor.adapters.opencode import OpenCodeAdapter
    from conductor.workspace import current_head, is_dirty, is_git_repo
    from conductor.security import redact

    objective = args.objective
    repo = args.repo or os.getcwd()
    db_path = args.db or DB_DEFAULT
    store = _store(db_path)

    # base commit
    base = current_head(repo) if is_git_repo(repo) else None

    run = Run(objective=objective, base_commit=base or "", integration_branch="integration")
    # criteria from args? simple: one criterion running a test command if provided
    if args.verify:
        run.criteria.append(Criterion(description="verify", verifier=args.verify, verifier_type="command"))
    store.save_run(run)

    engine = TaskEngine(store, run.run_id)
    sched = Scheduler(engine, store, run.run_id, max_concurrency=args.concurrency or 2)

    # register mock agent
    mock_agent = Agent(cli="mock", role="implementer", instance=0, workspace=repo)
    mock_adapter = MockCLI(MockBehavior(output="mock completed task", progress_events=2, delay=0.2))
    sched.register_agent(mock_agent, mock_adapter)

    # register opencode agent if available
    import shutil
    if shutil.which("opencode"):
        oc_agent = Agent(cli="opencode", role="implementer", instance=0, workspace=repo)
        oc_adapter = OpenCodeAdapter(model=args.model or "opencode/big-pickle")
        sched.register_agent(oc_agent, oc_adapter)

    # create task(s)
    task = engine.create_task(objective=objective, role="implementer")

    print(f"Run {run.run_id} started. Objective: {objective}")
    print("Press Ctrl+C to stop.")

    try:
        await sched.run_loop()
    except KeyboardInterrupt:
        print("Interrupted")
    # finalize
    run.state = "completed" if engine.all_done() else "stopped"
    store.save_run(run)
    print("Done. Tasks:")
    for t in engine.tasks.values():
        print(f"  {t.task_id}: {t.state}")


def cmd_status(args):
    store = _store(args.db)
    runs = store.list_runs()
    for r in runs[:10]:
        print(r["run_id"], r["state"], r["objective"][:60])
        tasks = store.list_tasks(r["run_id"])
        for t in tasks:
            print(f"   task {t['task_id']}: {t['state']} {t.get('failure_reason','')}")


def cmd_pause(args):
    print("pause not wired to running process; use API/UI. (stateless CLI)")


def cmd_resume(args):
    print("resume not wired; use API/UI.")


def cmd_cancel(args):
    print("cancel not wired; use API/UI.")


def cmd_logs(args):
    store = _store(args.db)
    run_id = args.run_id
    evs = store.list_events(run_id, limit=args.limit or 100)
    for e in reversed(evs):
        print(f"{e['timestamp']:.0f} [{e['type']}] {e.get('agent_id','')} {e.get('reason','')}")


def cmd_diagnose(args):
    import zipfile
    out = args.output or "conductor-diagnose.zip"
    store = _store(args.db)
    # build a redacted bundle
    import json
    data = {
        "runs": store.list_runs(),
        "tasks": store.list_tasks(),
        "agents": store.list_agents(),
        "events": store.list_events(limit=1000),
    }
    with open(out.replace(".zip", ".json"), "w") as f:
        from conductor.security import redact
        f.write(redact(json.dumps(data, indent=2, default=str)))
    print("wrote", out.replace(".zip", ".json"))


def main():
    parser = argparse.ArgumentParser(prog="conductor")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("doctor")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("run")
    p.add_argument("objective", nargs="?", default="Complete the task")
    p.add_argument("--repo", default=None)
    p.add_argument("--verify", default=None)
    p.add_argument("--concurrency", type=int, default=2)
    p.add_argument("--model", default=None)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_run)

    p = sub.add_parser("status")
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("logs")
    p.add_argument("run_id")
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_logs)

    p = sub.add_parser("diagnose")
    p.add_argument("--output", default=None)
    p.add_argument("--db", default=None)
    p.set_defaults(func=cmd_diagnose)

    p = sub.add_parser("pause")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(func=cmd_pause)
    p = sub.add_parser("resume")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(func=cmd_resume)
    p = sub.add_parser("cancel")
    p.add_argument("run_id", nargs="?")
    p.set_defaults(func=cmd_cancel)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()