# Contributing to hermes-kit

## TOF Core File Changes

Any commit that modifies TOF core files must include a family-different REVIEW.md:

### Core files (trigger CI review requirement)
- `TOF/tof`
- `TOF/orchestrator.py`
- `TOF/pipeline.yaml`
- `TOF/model_registry_adapter.py`
- `TOF/session_audit_adapter.py`
- `TOF/phases/**`

### How to generate a REVIEW.md

```bash
cd TOF
tof run --only review <run_dir>
```

This dispatches a single-phase review by a family-different model (as configured in pipeline.yaml: review phase uses gemini-3.1-pro-preview, which differs from establish's gpt-5.5).

The REVIEW.md must:
1. Be included in the same commit diff as the core file changes
2. Contain valid YAML frontmatter with `review.verdict` and `tof.reviewer` fields
3. Be produced by a model whose family differs from the establish phase model (CI enforces this)

See TOF/CORE_CONCEPTS.md for the full trust-chain architecture.
