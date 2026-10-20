# CLI Conductor

Multi-CLI autonomous orchestration application.

## Install
```
cd cli-conductor
python -m pip install -e .
```
Add `.../Python/pythoncore-3.12-64/Scripts` to PATH for `conductor` command, or use `python -m conductor`.

## Usage
```
conductor doctor
conductor run "your objective" --repo /path/to/repo --verify "pytest -q"
conductor status
conductor logs <run_id>
```
Web UI: `uvicorn conductor.api:create_app --factory` then open http://127.0.0.1:8000.

## Tests
```
python -m pytest
```

## Known limitations
- Only opencode exercised as real CLI (gemini/qwen not authenticated; claude/codex not installed).
- OS-level sandboxing not implemented (advisory).
- Kill/resume tested at lease-expiry level, not full process kill of orchestrator in CI.