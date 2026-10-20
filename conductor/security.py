import re
import os

# Patterns to redact
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|secret|password|passwd)\s*[:=]\s*['\"]?([A-Za-z0-9_\-]{8,})"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"AIza[A-Za-z0-9_\-]{30,}"),
]

DESTRUCTIVE_KEYWORDS = ["rm -rf", "reset --hard", "clean -fdx", "force-push", "push --force",
                        "drop database", "truncate", "delete from", "shutdown", "reboot",
                        "mkfs", "dd if="]


def redact(text: str, extra_secrets: list = None) -> str:
    if not text:
        return text
    out = text
    for pat in SECRET_PATTERNS:
        out = pat.sub(lambda m: m.group(0)[:6] + "***REDACTED***", out)
    for s in (extra_secrets or []):
        if s:
            out = out.replace(s, "***REDACTED***")
    return out


def is_destructive(command: str) -> bool:
    low = (command or "").lower()
    return any(k in low for k in DESTRUCTIVE_KEYWORDS)


def command_allowed(command: str, allowlist: list = None, denylist: list = None) -> bool:
    allowlist = allowlist or []
    denylist = denylist or []
    for d in denylist:
        if d in command:
            return False
    if allowlist:
        return any(a in command for a in allowlist)
    return True


def wrap_untrusted(content: str, provenance: str) -> str:
    return f"<untrusted provenance=\"{provenance}\">\n{content}\n</untrusted>"