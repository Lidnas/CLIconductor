# Security Model

## Enforcement actually achieved
- Sender derived from per-agent secret token by broker; payload sender ignored.
- Destructive command classifier for orchestrator-run commands.
- Secret redaction (regex patterns) in logs/UI/store.
- Process tree kill on cancel (taskkill /T on Windows, killpg on POSIX).
- Working directory confinement via git worktrees.
- Untrusted content wrapped with provenance labels; policy/budgets/criteria only mutable by authenticated user actions.

## Not achieved / advisory
- OS-level sandboxing (containers/seccomp) not implemented; enforcement is advisory + worktree confinement.
- Permission flags: default restrictive; "skip all permissions" requires explicit per-run opt-in (not implemented as flag passthrough; adapters use --auto for opencode only in worktree).
- No network egress filtering.

## Prompt injection defense
- Messages/files wrapped as `<untrusted provenance=...>` data.
- Broker validates typed purpose; rate limits per agent; collapses duplicates.
- Policy/budgets/criteria cannot be changed by agent output.