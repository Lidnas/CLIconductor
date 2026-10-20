# Architecture

## Requirements
Multi-CLI autonomous orchestration: coordinate multiple real AI coding CLI processes on one objective, with persisted state, kill/resume, cancellation, verification.

## Major decisions
- Language: Python 3.12 + asyncio (chosen) vs Go/Rust (faster but more deps/complexity). Chosen for ecosystem and FastAPI.
- Transport: FastAPI + WebSocket (chosen) vs gRPC (heavier). Chosen for simplicity and browser UI.
- Storage: SQLite WAL event store (chosen) vs Postgres (overkill for local).
- UI: simple HTML served by FastAPI.
- Dependencies minimized: fastapi, uvicorn, pydantic, click, httpx.

## Top 10 risks
1. CLI output format changes -> tolerant parser.
2. Process orphaning on crash -> process groups / job objects.
3. Lease expiry races -> fencing tokens.
4. False completion claims -> orchestrator-run verification.
5. Stagnation -> hash-based detection.
6. Secret leakage -> redaction layer.
7. Prompt injection -> untrusted wrapping + policy gate.
8. Merge conflicts -> integration branch + verify.
9. Circular deps -> DAG cycle detection.
10. Stale assignments -> lease expiry + reassign.