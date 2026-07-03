#!/usr/bin/env python3
"""TOF Orchestrator — receipt-driven state machine loop.

Dispatches OT subprocesses, calls SessionAuditAdapter, merges metadata,
re-runs tof validate.  Stateless and idempotent.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run(run_dir: str, step_mode: bool = False) -> int:
    """Orchestrate a TOF run to completion (or single step)."""
    rd = Path(run_dir).resolve()
    if not rd.exists():
        print(f"Creating run directory: {rd}")
        rd.mkdir(parents=True)

    tof_bin = _find_tof_bin()
    pipeline = _load_pipeline(tof_bin.parent)
    models_registry = _load_models(tof_bin.parent)

    max_iter = 20
    for _ in range(max_iter):
        receipt = _tof_validate(tof_bin, rd)
        status = receipt["validation"]["status"]
        phase = receipt["validation"].get("phase")
        next_allowed = receipt["validation"].get("next_allowed", [])
        frontier = receipt["validation"].get("causal_frontier")

        print(f"  [{status}] phase={phase} next={next_allowed}")

        # Terminal: pipeline complete
        if status == "PASS" and frontier and frontier.get("phase") in ("verify", "deposition"):
            print("DONE — pipeline complete.")
            return 0

        # Terminal: INVALID artifact
        if status == "INVALID":
            reasons = receipt["validation"].get("reasons", [])
            print(f"STOP — INVALID artifact. Reasons:")
            for r in reasons:
                print(f"  - {r}")
            return 1

        # Terminal: PENDING — start from clarify
        if status == "PENDING":
            next_phase = next_allowed[0] if next_allowed else "clarify"
        elif status == "BLOCKING":
            if not next_allowed:
                print("STOP — BLOCKING with no next phase, escalation required.")
                return 1
            next_phase = next_allowed[0]
        elif next_allowed:
            next_phase = next_allowed[0]
        else:
            print("STOP — unknown state.")
            return 1

        if step_mode:
            print(f"  STEP: next phase = {next_phase}")
            print(f"  Run: tof run {rd} to continue")
            return 0

        # Dispatch OT subprocess
        phase_cfg = pipeline["phases"].get(next_phase)
        if not phase_cfg:
            print(f"STOP — phase '{next_phase}' not found in pipeline.yaml")
            return 1
        assigned_model = phase_cfg.get("model")
        if not assigned_model:
            print(f"STOP — phase '{next_phase}' has no model assignment")
            return 1

        print(f"  → dispatching {next_phase} via {assigned_model} ...")
        try:
            session_id = _dispatch_ot(tof_bin.parent, next_phase, assigned_model, rd, pipeline)
        except RuntimeError as e:
            print(f"STOP — OT dispatch failed: {e}")
            return 1

        # Session audit
        try:
            from session_audit_adapter import read_session as audit

            log_path = os.path.expanduser("~/.hermes/logs/agent.log")
            result = audit(session_id, log_path, assigned_model, models_registry)
            _write_metadata(rd, next_phase, session_id, result)
            print(f"  metadata: actual={result['actual_model']} "
                  f"fallback={result['fallback_detected']} "
                  f"confidence={result['verification_confidence']}")
        except Exception as e:
            print(f"  WARNING: session audit failed ({e}), continuing without metadata")

        time.sleep(0.5)

    print("STOP — max iterations reached.")
    return 1


# ---------------------------------------------------------------------------
# Internal: tof validate invocation
# ---------------------------------------------------------------------------

def _tof_validate(tof_bin: Path, run_dir: Path) -> Dict[str, Any]:
    proc = subprocess.run(
        [sys.executable, str(tof_bin), "validate", str(run_dir)],
        capture_output=True, text=True, timeout=30,
    )
    if proc.returncode not in (0, 1):
        raise RuntimeError(f"tof validate failed: {proc.stderr}")
    return json.loads(proc.stdout)


def _find_tof_bin() -> Path:
    """Locate tof script (alongside this module or in parent TOF dir)."""
    this_dir = Path(__file__).resolve().parent
    for cand in [this_dir / "tof", this_dir / ".." / "TOF" / "tof"]:
        if cand.exists():
            return cand.resolve()
    raise FileNotFoundError("cannot find tof script relative to orchestrator")


# ---------------------------------------------------------------------------
# Internal: dispatch
# ---------------------------------------------------------------------------

_SESSION_RE = re.compile(r"Session:\s+(\S+)")


def _dispatch_ot(tof_dir: Path, phase: str, model: str, run_dir: Path,
                 pipeline: Dict[str, Any]) -> str:
    """Run hermes chat -q, parse session ID from output, write artifact to run_dir."""
    prompt_path = tof_dir / "phases" / phase / "prompt.md"
    if not prompt_path.exists():
        raise RuntimeError(f"prompt file not found: {prompt_path}")

    prompt = prompt_path.read_text()

    # Append upstream artifact context
    upstream = _build_upstream_context(run_dir, phase, pipeline)
    if upstream:
        prompt += "\n\n## Upstream Artifacts\n\n" + upstream

    # Determine provider from model — fallback to the model's known provider
    provider = "deepseek" if model.startswith("deepseek") else "openrouter"

    cmd = [
        "hermes", "chat", "-q", prompt,
        "--provider", provider,
        "--model", model,
    ]

    # Write prompt to temp file for hermes to read cleanly
    prompt_file = run_dir / f".hermes_prompt_{phase}.txt"
    prompt_file.write_text(prompt)

    proc = subprocess.run(
        cmd, capture_output=True, text=True, timeout=300,
        cwd=str(run_dir),
    )

    output = proc.stdout
    if not output:
        output = proc.stderr
    if not output:
        raise RuntimeError(f"hermes chat produced no output (exit {proc.returncode})")

    # Extract session ID
    m = _SESSION_RE.search(output)
    if not m:
        # Try to find session ID in any format
        session_match = re.search(r'\b\d{8}_\d{6}_[a-f0-9]+\b', output)
        if session_match:
            session_id = session_match.group(0)
        else:
            # Write output for debugging and fail gracefully
            debug_file = run_dir / f".hermes_debug_{phase}.txt"
            debug_file.write_text(output)
            raise RuntimeError(f"cannot find session ID in output; wrote debug to {debug_file}")
    else:
        session_id = m.group(1)

    # Derive artifact filename from phase order
    phase_order = list(pipeline.get("phases", {}).keys())
    phase_idx = phase_order.index(phase) if phase in phase_order else 0
    artifact_name = f"{phase_idx:02d}-{phase.capitalize()}.md"
    artifact_path = run_dir / artifact_name

    # Strip ANSI escapes and box-drawing chars, extract model response
    clean = _strip_ansi(output)
    body = _extract_response_body(clean)
    if not body:
        body = clean  # fallback: use everything

    artifact_path.write_text(body)
    print(f"  wrote artifact: {artifact_path.name} ({len(body)} chars)")

    return session_id


def _strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences and carriage returns."""
    return re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text).replace('\r\n', '\n').replace('\r', '\n')


def _extract_response_body(text: str) -> str:
    """Extract the model's textual response from hermes TUI output.
    
    Looks for content between TUI framing markers or strips the session footer.
    """
    # Strip session summary footer
    lines = text.split('\n')
    cleaned = []
    for line in lines:
        if 'Resume this session with:' in line:
            break
        if re.match(r'^(Session:|Duration:|Messages:|Query:|Initializing)', line.strip()):
            continue
        if line.strip().startswith('╭') or line.strip().startswith('╰'):
            continue
        if line.strip().startswith('──') or line.strip().startswith('──'):
            continue
        cleaned.append(line)
    
    body = '\n'.join(cleaned).strip()
    # Remove leading hermes header lines
    body = re.sub(r'^.*Hermes\s+Agent.*\n', '', body)
    return body.strip()


# ---------------------------------------------------------------------------
# Internal: prompt construction
# ---------------------------------------------------------------------------

def _build_upstream_context(run_dir: Path, phase: str, pipeline: Dict[str, Any]) -> str:
    """Read upstream artifacts listed in pipeline.yaml inputs for this phase."""
    phase_cfg = pipeline.get("phases", {}).get(phase, {})
    inputs_cfg = phase_cfg.get("inputs", {})
    required = inputs_cfg.get("required", [])

    context_parts = []
    for src_phase in required:
        # Find artifact for this source phase in run_dir
        for f in sorted(run_dir.glob("*.md"), reverse=True):
            try:
                import yaml
                text = f.read_text()
                if text.startswith("---"):
                    end = text.find("---", 3)
                    if end > 0:
                        fm = yaml.safe_load(text[3:end]) or {}
                        if fm.get("tof", {}).get("phase") == src_phase:
                            context_parts.append(f"### {src_phase}\n\n{text[end+3:].strip()}")
                            break
            except Exception:
                continue

    return "\n\n".join(context_parts)


# ---------------------------------------------------------------------------
# Internal: metadata
# ---------------------------------------------------------------------------

def _write_metadata(run_dir: Path, phase: str, session_id: str,
                    result: Dict[str, Any]) -> None:
    """Write session-metadata.json alongside artifacts."""
    path = run_dir / f".session-metadata-{phase}.json"
    payload = {
        "phase": phase,
        "session_id": session_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "assigned_model": result.get("assigned_model", "?"),
        "actual_model": result["actual_model"],
        "actual_family": result["actual_family"],
        "fallback_detected": result["fallback_detected"],
        "provider": result["provider"],
        "latency_ms": result["latency_ms"],
        "verification_confidence": result["verification_confidence"],
        "verification_method": result["method"],
    }
    path.write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Internal: config loading
# ---------------------------------------------------------------------------

def _load_pipeline(tof_dir: Path) -> Dict[str, Any]:
    import yaml
    path = tof_dir / "pipeline.yaml"
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_models(tof_dir: Path) -> Dict[str, Any]:
    import yaml
    path = tof_dir / "models.yaml"
    with open(path) as f:
        return (yaml.safe_load(f) or {}).get("models", {})


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(prog="tof-run", description="TOF Orchestrator")
    parser.add_argument("run_dir", help="TOF run directory")
    parser.add_argument("--step", action="store_true", help="Single-step mode")
    args = parser.parse_args()
    sys.exit(run(args.run_dir, step_mode=args.step))
