# CLI Capability Report

| CLI | Version | Available | Auth | Headless | JSON output | Session resume | MCP | Notes |
|---|---|---|---|---|---|---|---|---|
| opencode | 2.0.32 | YES | configured (free models) | `opencode run --format json` | yes (stream-json-ish via JSON lines) | `--session <id>` / `--continue` | yes (`opencode mcp`) | Used as real CLI in tests |
| gemini | 0.46.0 | YES | NO (no API key) | `-p` headless | `-o json/stream-json` | `--resume` | yes | Marked UNAVAILABLE for real runs (no credentials) |
| qwen | 0.20.0 | YES | NO | `-p` headless | `-o json` | `--resume` | yes | Not authenticated; not exercised |
| claude | n/a | NO | n/a | n/a | n/a | n/a | n/a | Not installed |
| codex | n/a | NO | n/a | n/a | n/a | n/a | n/a | Not installed |

## Verified behavior (opencode)
- Headless invocation: `opencode run --format json --model <m> --auto <prompt>` returns JSON lines with sessionID and text parts.
- Exit code 0 on success.
- Session resume via `--session <native_session_id>`.
- MCP support present (`opencode mcp list/add`).

## Unverified
- gemini/qwen real execution: no credentials. Claims downgraded accordingly.