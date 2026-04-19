"""App commit-hash resolution for the version footer.

Computed once at import time. Tries `git rev-parse --short HEAD` first
(works in Codespace / any checkout with a .git dir and git installed),
then falls back to well-known deploy-platform env vars, then to
"unknown". Cached as a module constant so every /version request is
cheap.
"""

from __future__ import annotations

import os
import subprocess


def _resolve_commit_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass

    for env_var in ("GIT_COMMIT", "RAILWAY_GIT_COMMIT_SHA"):
        val = os.getenv(env_var, "").strip()
        if val:
            return val[:7]  # short-hash convention

    return "unknown"


COMMIT_HASH = _resolve_commit_hash()
