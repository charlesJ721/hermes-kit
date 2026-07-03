# Implementation Status

> What works today, what's deferred, and what's out of scope.

## MECHANICAL — Enforced by `tof validate`

All checks below produce INVALID receipts when violated. Backed by 14 fixture tests.

| Constraint | Mechanism | Since |
|-----------|-----------|-------|
| Schema validation | `validate_schema()` checks frontmatter dotted paths against pipeline.yaml | P0.1 |
| Input lineage | `validate_input_linkage()` — path+phase+sha256 resolution, required/required_if_present | P0.2a |
| Stale downstream detection | `check_stale()` + `apply_stale_to_all()` — global artifact truth | P0.2a |
| Model family diversity | `model_policy.family_must_differ_from` — registry-backed check | P0.1 |
| Model family consistency | `actual_family` must match `models.yaml[assigned_model].family` | P0.2b |
| Retry budget | `validate_retry_budget()` — `>=max_rounds` → escalation | P0.1 |
| Verdict validation | Invalid verdict → INVALID | P0.1 |
| Config source tracking | Receipt embeds `pipeline_path` + `pipeline_sha256` + `models_path` + `models_sha256` | P0.3 |
| Model freshness | `model_freshness.max_staleness_days` + `on_stale` (warning/blocking) | post-review |
| Timeout policy validation | `timeout_policy` struct check in lint-pipeline | post-review |

## BEHAVIORAL — Documented protocol, not enforced by code

These are documented for correct operation. Violations are detectable by a human auditor but do not produce INVALID receipts.

| Protocol | Documented in | Notes |
|----------|-------------|-------|
| STATE_LOCKER | CORE_CONCEPTS.md | Interactive UX protocol; no runtime interceptor exists |
| Orchestrator behavior boundaries | CORE_CONCEPTS.md | Orchestrator must not do downstream phase work; enforced by discipline |
| OT verification (who actually ran) | OT.md | Manual: session records + cross-session audit + API log trace |
| Phase EX escalation | PHASES.md | Human-in-the-loop decision; validator detects condition but routing is manual |

## DEFERRED — Adapter implementations not yet built

These are defined in `adapter-contract.md` but have no real implementation yet. P0 uses fake adapters that construct facts from artifact frontmatter.

| Adapter | Status |
|---------|--------|
| DispatchAdapter | Fake: model identity from frontmatter `produced_by`, not from an actual dispatch system |
| SessionAuditAdapter | Not implemented: no way to independently verify `actual_model`/`actual_family`/`fallback_detected` |
| ArtifactStore | Inline: reads `.md` files directly from the filesystem |
| ModelRegistryAdapter | Not implemented: model slug freshness checked manually |
| KnowledgeDepositionAdapter | Not implemented |
| ApprovalAdapter | Not implemented |

## OUT OF SCOPE — Design boundaries

| Topic | Why | 
|-------|-----|
| Parallel task execution | TOF handles single linear pipelines; parallel task splitting is a different scheduling problem |
| Partially-completed Implement rollback | If Implement fails at 80%, work is discarded — no checkpoint/resume |
| Review content quality assessment | TOF verifies Review artifact exists with different model family, not whether the review is substantive |
| End-to-end pipeline execution | TOF validates artifacts; it does not execute model dispatches or orchestrate the pipeline | 

## Cold-Read Review

This framework should periodically receive **cold-read review** from someone unfamiliar with its internals. Designers are blind to the gaps that new users discover immediately. The review that produced this document found several issues that internal review would not have caught:

- An external reviewer looking for `model_freshness` fields in the wrong file surfaced the CODEX/DATA separation design intent — a feature, not a bug, but only visible through outsider confusion
- `on_stale` was described as `blocking` in documentation but implemented as `warning` — only caught by cross-referencing code against claims
- The double-retry system (`timeout_policy` vs per-phase `retry`) was never explicitly documented until an outsider asked "how do these relate?"

Convention: before each major version bump, invite a cold-read review. The reviewer should not read the documentation first — they should try to use the system and report what breaks.
