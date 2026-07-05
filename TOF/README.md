# TOF — Task Orchestration Framework

[![TOF v4](https://img.shields.io/badge/TOF-v4-blue)](https://github.com/charlesJ721/hermes-kit/tree/main/TOF)
[![Tests](https://img.shields.io/badge/tests-18%20PASS-brightgreen)]()
[![Pipeline](https://img.shields.io/badge/lint-0%20errors%200%20warnings-success)]()
[![License](https://img.shields.io/badge/license-MIT-orange)]()

> **Multi-model pipeline with built-in self-audit. 4 files of code, 18 test fixtures, zero mocks. Fail-closed by default.**

TOF routes complex AI tasks through a 7-phase pipeline where each phase uses a different model, runs in an isolated context, and produces a structured artifact that gets independently validated. One broken phase → all downstream phases marked INVALID. Nothing rots silently.

---

## What it does

```
Your task: "Refactor the auth module to support OIDC"

  Clarify (GPT-5.5)     → 00-Clarify.md    scope, exclusions, success criteria
  Scout   (Claude Opus) → 01-Scout.md      affected files, risks, unknowns
  Establish (GPT-5.5)   → 02-Establish.md  solution design, PLAN.md
  Review  (Gemini)      → 03-Review.md     adversarial review, BLOCKING findings
  Implement (GPT-5.5)   → code changes     per approved plan
  Verify  (DeepSeek)    → 05-Verify.md     cross-check against plan
  Deposition            → knowledge archive

  Every artifact validated by tof validate:
  schema → input lineage → staleness → model family → session audit → cascade
```

Each phase runs as an isolated OT subprocess. No shared context. No model-sharing blind spots.

---

## One minute

```bash
# Install
pip install pyyaml
git clone https://github.com/charlesJ721/hermes-kit.git
cd hermes-kit/TOF

# Validate a sample pipeline run
./tof validate test-fixtures/test-smoke-full-pipeline \
  --pipeline pipeline.yaml --models models.yaml

# Check your own pipeline definition
./tof lint-pipeline --pipeline pipeline.yaml

# Run all 18 test fixtures
python3 tests_expected.py
# → all expected TOF fixture semantics passed
```

---

## The five validation checks

Every artifact goes through five independent checks before passing the gate:

| Check | What it catches |
|-------|----------------|
| **schema** | Missing required fields, wrong types, invalid frontmatter |
| **input linkage** | SHA256 mismatch between declared upstream and actual artifact |
| **staleness** | Downstream artifact that wasn't rebuilt after upstream changed |
| **model family** | Artifact claims model family X but registry says Y |
| **session audit** | Agent log shows a different model ran than what was assigned |

One INVALID check → all downstream artifacts cascade to INVALID. Fail-closed.

---

## Model diversity (SERI audit)

TOF ships with a self-audit pipeline (SERI) that verifies the framework against itself using 4 different model families:

| Phase | Model | Family | Audit result |
|-------|-------|--------|-------------|
| Scout | Claude Opus 4.8 | claude | verified_match |
| Establish | GPT-5.5 | gpt | verified_match |
| Review | Gemini 3.1 Pro | gemini | verified_match |
| Verify | DeepSeek v4 Pro | deepseek | verified_match |

**Zero overlapping findings across 4 families.** `family_must_differ` works.

---

## Why not LangChain / CrewAI / AutoGen

Those frameworks ask "what should the agent do next?" — TOF asks **"who should do this, and can we prove they actually did it?"**

| | LangChain/CrewAI | TOF |
|---|:-:|:-:|
| Multi-model pipeline | ✅ | ✅ |
| Independent phase isolation | ❌ shared context | ✅ isolated OT subprocesses |
| Built-in validation gate | ❌ manual review | ✅ 5 automatic checks |
| Session audit (model identity) | ❌ | ✅ agent.log parser |
| Fail-closed by default | ❌ | ✅ cascade invalidation |
| Test fixtures | varies | ✅ 18, all PASS |
| Dependencies | 30+ packages | 1 (pyyaml) |

---

## Project structure

```
TOF/
├── tof                         # Validator (1324 lines): 5 checks + cascade
├── orchestrator.py             # State machine: OT dispatch, receipt loop
├── session_audit_adapter.py    # Agent.log parser: model identity verification
├── model_registry_adapter.py   # Provider endpoint checker: slug freshness
├── pipeline.yaml               # 7-phase DAG + transition rules + policies
├── models.yaml                 # 7 models × 4 families
├── tests_expected.py           # 18 fixture semantics validator
├── test-fixtures/              # 18 synthetic pipeline runs
├── phases/                     # Prompt templates per phase
└── IMPLEMENTATION_STATUS.md    # What's built, what's pending, known gaps
```

---

## Philosophy

TOF was not designed from first principles. Every mechanism — the 5 checks, cascade invalidation, session audit, model family enforcement — was added to fix a real failure observed during development. The failures are documented alongside the fixes.

> **"An unverifiable pipeline is a fake pipeline."**

---

## License

MIT
