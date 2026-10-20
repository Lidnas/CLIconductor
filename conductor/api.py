import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from conductor.db import Store
from conductor.models import Run, Criterion
from conductor.task_engine import TaskEngine
from conductor.scheduler import Scheduler
from conductor.adapters.opencode import OpenCodeAdapter
from conductor.security import redact
from conductor.verifier import Verifier


def create_app(db_path: str = None):
    import os as _os
    if db_path is None:
        try:
            from conductor.resources import data_dir as _dd
            _, st = _dd()
            db_path = _os.path.join(st, "conductor.db")
        except Exception:
            db_path = _os.path.join(_os.getcwd(), ".conductor", "conductor.db")
    _os.makedirs(_os.path.dirname(db_path), exist_ok=True)
    store = Store(db_path)
    app = FastAPI(title="CLI Conductor")
    app.state.store = store
    app.state.runs = {}  # run_id -> (engine, scheduler, task)
    app.state.ws_clients = set()

    async def broadcast(msg):
        dead = []
        for ws in list(app.state.ws_clients):
            try:
                await ws.send_text(json.dumps(msg, default=str))
            except Exception:
                dead.append(ws)
        for d in dead:
            app.state.ws_clients.discard(d)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/")
    async def index():
        try:
            from conductor.resources import resource_path
            ui = resource_path(os.path.join("conductor", "ui", "index.html"))
        except Exception:
            ui = _os.path.join(_os.path.dirname(__file__), "ui", "index.html")
        if _os.path.exists(ui):
            return FileResponse(ui)
        return HTMLResponse("<h1>CLI Conductor</h1>")

    @app.get("/api/runs")
    async def list_runs():
        return store.list_runs()

    @app.post("/api/runs")
    async def create_run(body: dict):
        objective = body.get("objective", "task")
        repo = body.get("repo", _os.getcwd())
        from conductor.models import Run
        from conductor.workspace import current_head
        run = Run(objective=objective, base_commit=current_head(repo) or "", integration_branch="integration")
        store.save_run(run)
        engine = TaskEngine(store, run.run_id)
        sched = Scheduler(engine, store, run.run_id, max_concurrency=body.get("concurrency", 2))
        # register mock agent
        import shutil
        if not shutil.which("opencode"):
            raise HTTPException(status_code=400, detail="OpenCode not found. Install OpenCode and authenticate before running.")
        from conductor.models import Agent
        oa = Agent(cli="opencode", role="implementer", instance=0, workspace=repo)
        sched.register_agent(oa, OpenCodeAdapter(model=body.get("model", "opencode/big-pickle")))
        task = engine.create_task(objective=objective, role="implementer")
        app.state.runs[run.run_id] = (engine, sched, task)
        # start loop in background
        async def loop():
            await sched.run_loop()
            run.state = "completed" if engine.all_done() else "stopped"
            store.save_run(run)
            await broadcast({"type": "run_done", "run_id": run.run_id})
        asyncio.create_task(loop())
        await broadcast({"type": "run_created", "run_id": run.run_id})
        return {"run_id": run.run_id}

    @app.get("/api/runs/{run_id}/tasks")
    async def tasks(run_id):
        return store.list_tasks(run_id)

    @app.get("/api/runs/{run_id}/agents")
    async def agents(run_id):
        return store.list_agents(run_id)

    @app.get("/api/runs/{run_id}/messages")
    async def messages(run_id):
        return store.list_messages(run_id=run_id)

    @app.get("/api/runs/{run_id}/events")
    async def events(run_id, limit: int = 200):
        return store.list_events(run_id, limit=limit)

    @app.post("/api/runs/{run_id}/pause")
    async def pause(run_id):
        e, s, _ = app.state.runs[run_id]
        await s.pause()
        return {"ok": True}

    @app.post("/api/runs/{run_id}/pause_all")
    async def pause_all(run_id):
        e, s, _ = app.state.runs[run_id]
        await s.pause_all()
        return {"ok": True}

    @app.post("/api/runs/{run_id}/resume")
    async def resume(run_id):
        e, s, _ = app.state.runs[run_id]
        await s.resume()
        return {"ok": True}

    @app.post("/api/runs/{run_id}/cancel")
    async def cancel(run_id):
        e, s, _ = app.state.runs[run_id]
        s.stop()
        e.cancel_run_tasks()
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket):
        await websocket.accept()
        app.state.ws_clients.add(websocket)
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            app.state.ws_clients.discard(websocket)

    return app