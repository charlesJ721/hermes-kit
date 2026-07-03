"""SessionAuditAdapter — reads agent.log to verify which model actually executed.

P0 Minimal implementation. Parses agent.log API call lines.
Agreed interface: read_session(session_id, log_path, assigned_model, models_registry) -> dict.
Adapters return facts, do not orchestrate.  Orchestrator merges output into metadata.json.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------

def read_session(
    session_id: str,
    log_path: str,
    assigned_model: str,
    models_registry: Dict[str, Any],
) -> Dict[str, Any]:
    """Read agent.log and return observed model facts.

    Returns a dict with the agreed SessionAuditAdapter output schema.
    Orchestrator merges this into metadata.json; tof validate reads the merge.
    """
    path = Path(log_path).expanduser()
    if not path.exists():
        return _unverified_result("log file not found")

    try:
        lines = _grep_session(path, session_id)
    except OSError:
        return _unverified_result("cannot read log file")

    calls = _parse_api_calls(lines)
    if not calls:
        return _unverified_result("no API calls found for session")

    first = calls[0]
    actual_model = first.get("model") or None
    provider = first.get("provider") or None
    latency_ms = _parse_latency(first.get("latency"))

    # Determine fallback: API call #2 exists → True; only #1 → False
    fallback_detected: Optional[bool] = None
    if len(calls) > 1:
        # Check if subsequent calls used a different model (not just retry of same)
        for c in calls[1:]:
            if c.get("model") and c["model"] != actual_model:
                fallback_detected = True
                break
        if fallback_detected is None:
            fallback_detected = False  # same model retried, not a fallback
    else:
        fallback_detected = False

    actual_family: Optional[str] = None
    if actual_model and actual_model in models_registry:
        actual_family = models_registry[actual_model].get("family")

    # Verify assigned_model matches actual
    if actual_model and assigned_model and actual_model != assigned_model:
        fallback_detected = True  # override: model mismatch from first call

    return {
        "actual_model": actual_model,
        "actual_family": actual_family,
        "fallback_detected": fallback_detected,
        "provider": provider,
        "latency_ms": latency_ms,
        "verification_confidence": 0.7 if actual_model else 0.0,
        "method": "log_parsed" if actual_model else "unverified",
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_CALL_LINE_RE = re.compile(
    r"API call #(?P<n>\d+):\s*"
    r"model=(?P<model>\S+)\s+"
    r"provider=(?P<provider>\S+)\s+"
    r".*?latency=(?P<latency>[\d.]+)s"
)


def _grep_session(log_path: Path, session_id: str) -> list[str]:
    """Return all log lines containing session_id and 'API call'."""
    result: list[str] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if session_id in line and "API call" in line:
                result.append(line.rstrip("\n"))
    return result


def _parse_api_calls(lines: list[str]) -> list[dict[str, str]]:
    """Parse API call lines, ordered by call number."""
    calls: list[tuple[int, dict[str, str]]] = []
    for line in lines:
        m = _CALL_LINE_RE.search(line)
        if m:
            calls.append((int(m.group("n")), {
                "model": m.group("model"),
                "provider": m.group("provider"),
                "latency": m.group("latency"),
            }))
    calls.sort(key=lambda x: x[0])
    return [c[1] for c in calls]


def _parse_latency(raw: Optional[str]) -> Optional[int]:
    """Parse latency string (e.g. '2.7') → milliseconds."""
    if raw is None:
        return None
    try:
        return int(float(raw) * 1000)
    except (ValueError, TypeError):
        return None


def _unverified_result(reason: str) -> Dict[str, Any]:
    """Return a result with null model fields — log unavailable."""
    return {
        "actual_model": None,
        "actual_family": None,
        "fallback_detected": None,
        "provider": None,
        "latency_ms": None,
        "verification_confidence": 0.0,
        "method": "unverified",
        "unverified_reason": reason,
    }
