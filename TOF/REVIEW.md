---
tof:
  run_id: "tof-mindmemos"
  phase: "review"
  schema_version: "0.1"
  round: 1
  produced_by:
    adapter: "fake"
    assigned_model: "google/gemini-3.1-pro-preview"
    claimed_model: "google/gemini-3.1-pro-preview"
    assigned_family: "gemini"
    actual_family: "gemini"
  inputs:
    - phase: "establish"
      path: "TOF/PLAN.md"
review:
  verdict: "APPROVED_WITH_MODIFICATIONS"
  adversarial_findings:
    - id: "finding-p0-safety"
      severity: "critical"
      target_step: "p0-current-adapter-hardening"
      finding: "The current memory_dreaming_adapter.py has a critical execution bug. The json.load reconstruction in CLI lacks the explicit '__init__()' mapping for 'id' to 'action_id'. Calling --safe-only crashes with 'TypeError: __init__() got an unexpected keyword argument 'id''. We cannot build v2 on an adapter that crashes in its execution path."
      recommendation: "P0 must include fixing the dict expansion in the '--safe-only' CLI block so 'id' maps to 'action_id'. The current test suite must add a test covering execution, not just dry runs."
    - id: "finding-split-brain"
      severity: "high"
      target_step: "p2-quality-signals"
      finding: "fact_store is read directly via sqlite3 in _load_all_entries(), but facts are missing index values mapping back to MEMORY / USER indices. If memory_entry_hashes or memory_quality_signals uses entry_refs like 'FACT[10]', it's brittle if fact_store dynamically changes rowids. fact_store uses fact_id as primary key, which is stable, but linking it via string 'FACT[10]' loses referential integrity if the SQLite scheme evolves."
      recommendation: "Ensure entry_refs natively map to 'fact_id' in a standard way, and document that fact_store modifications MUST cascade or orphans will exist in memory_entry_hashes."
    - id: "finding-content-hash-risk"
      severity: "medium"
      target_step: "p1-entry-identity-and-content-hash"
      finding: "Content hash normalization strips whitespace, but trailing/leading metadata (like timestamps) aren't handled predictably across MEMORY vs USER. The plan mentions stripping volatile date prefixes 'only when explicitly marked as metadata', but flat text lacks metadata boundaries. This will cause false deduplication misses."
      recommendation: "Add a clear regex whitelist for date prefix stripping (e.g., '(YYYY-MM-DD)') in _normalize_content rather than relying on abstract 'metadata' markers."
    - id: "finding-deep-mode-dependency"
      severity: "low"
      target_step: "p5-optional-dual-llm-dreaming"
      finding: "Using `subprocess.run(['hermes', 'chat', '-q', ...])` adds no Python package, but it tightly couples the database logic to the CLI process context. If run via cron, the environment might lack the correct Hermes profile or auth context."
      recommendation: "Deep mode must explicitly pass '--profile' or inherit the environment carefully. Added risk is acceptable given it's opt-in."
    - id: "finding-destructive-bypass"
      severity: "high"
      target_step: "p4-detect-then-act-pipeline"
      finding: "The plan proposes moving issue detection and action planning out, but _apply_review_gates still operates on the final actions. If the LLM proposes a 'RELOCATE', but _apply_review_gates only checks 'COMPRESS' or 'REMOVE' (as it does currently for Triage rules), a destructive action could slip through."
      recommendation: "Expand all four BLOCKING gates in _apply_review_gates to inspect all file-mutating action types (MERGE, COMPRESS, REMOVE, DEDUP, UPDATE), ensuring no destructive action is missed."
  verification_adjustments:
    - "Add test: 'python3 memory_dreaming_adapter.py --safe-only' runs without crashing on an empty actions list or mock actions."
    - "Add test: verify _apply_review_gates blocks a DEDUP action containing a Triage rule target."
  next_phase_guidance: "Implement phase MUST fix the CLI dict expansion bug in P0 before writing any new architecture. Do not skip tests for execute_safe_actions()."
---
# TOF Review Report — Hermes Memory System v2

## 1. Safety and Execution Context (P0 Focus)

The Establish plan correctly identified that hardening the current adapter (P0) is a prerequisite. However, it missed a critical, verifiable bug currently in production: **the `--safe-only` execution path crashes immediately.**

By running `python3 memory_dreaming_adapter.py --safe-only` in the workspace, I verified it crashes with `TypeError: __init__() got an unexpected keyword argument 'id'`. This happens because `json.dumps` aliases `action_id` to `id`, but the reconstruction logic `Action(**{k: v for k, v in a.items() if k != 'blocked'})` passes `id` directly to `Action()`, which expects `action_id`.

**Mandatory Change:** Implementation MUST fix this dict expansion bug in P0. We cannot build architecture on a broken executor.

## 2. Split-Brain Risk with `fact_store`

P3 proposes adding `memory_relations`, `memory_quality_signals`, and `memory_entry_hashes` to the existing SQLite `memory_store.db`. This is correct ("万源归宗"), but using string `entry_ref` values like "FACT[10]" to reference `fact_store.facts(fact_id)` creates a weak link.
*   **Risk:** SQLite `fact_store` handles its own lifecycle. If a fact is deleted via `fact_store` APIs, orphaned rows will pollute the new `memory_*` tables.
*   **Adjustment:** Document and enforce that `memory_entry_hashes` and `memory_relations` act as non-authoritative fast-lookups. If a referenced `FACT[10]` is missing from the core `facts` table during load, the orphaned signal rows should be cleared harmlessly.

## 3. False Deduplication Misses (P1 Focus)

P1 proposes `_normalize_content` to strip volatile date prefixes "only when explicitly marked as metadata, not inside fact content." Since `MEMORY.md` is plain flat text, this distinction is impossible without explicit regex.

*   **Risk:** Without a concrete date-stripping regex, `(2026-07-01) VPS setup` and `(2026-07-02) VPS setup` will hash differently, defeating the exact-dedup fast path.
*   **Adjustment:** Implement a hardcoded regex whitelist for known date prefixes (e.g., `(YY/MM/DD)`, `(YYYY-MM-DD)`) in the normalization function.

## 4. Destructive Bypass in Review Gates (P4 Focus)

P4 splits detect from act, which is excellent. However, `_apply_review_gates` is currently hardcoded in its conditionals (e.g., Gate 1 only blocks `COMPRESS` and `REMOVE`). P3 introduces `MERGE` and `DEDUP`.

*   **Risk:** If the new action taxonomy is not fully respected by the old gates, an LLM could propose a `MERGE` or `RELOCATE` on a protected Triage rule, and the gate would happily pass it because it only checks for `COMPRESS/REMOVE`.
*   **Adjustment:** The `_apply_review_gates` function MUST be updated alongside the action taxonomy expansion to ensure **all file-mutating operations** involving protected entities are strictly policed.

## 5. Summary

The Establish architecture is sound and strictly adheres to the "no new isolated apps" (万源归宗) philosophy. The decision to use SQLite side tables attached to the existing event loop rather than introducing Qdrant or Neo4j is accurate for the current scale.

I assign `APPROVED_WITH_MODIFICATIONS`. Proceed to Implement, but P0 must contain the executor crash fix.
