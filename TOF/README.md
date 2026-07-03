# Task Orchestration Framework (TOF)

> A multi-model, multi-phase agent orchestration pipeline that prevents the single most expensive failure mode in LLM agents: **the agent doing everything itself with one model.**

**What TOF solves:** When you give an AI agent a non-trivial task — a refactor, a system diagnosis, an architectural decision — the agent's default instinct is to do everything itself: plan, code, review, verify. This is fast but brittle. Every step inherits the same model's blind spots. No independent verification ever happens. Bad assumptions compound.

TOF enforces a different default: **orchestrate, don't execute.** For any non-trivial task, TOF routes the work through a five-phase pipeline where each phase uses a different model, runs in an isolated context, and produces a structured contract consumed by the next phase.

## Quick Start

```bash
# 1. Classify your task
Task: "Refactor the auth module to support OIDC"
→ Domain: engineering  |  Complexity: L2 (3+ files)  |  Cost of failure: medium
→ Route: Standard SERI (5-phase full pipeline)

# 2. Run the pipeline
Phase 0 — Clarify   (model A): Define scope, success criteria, exclusions
Phase 1 — Scout     (model B): Research affected files, risks, unknowns
Phase 2 — Establish (model C): Design the solution, write PLAN.md
Phase 3 — Review    (model D): Adversarial review, find blind spots
Phase 4 — Implement (model C): Execute per approved plan
Phase 5 — Verify    (model A): Cross-check against plan
```

## Core Concepts

- **Five-phase pipeline** — Clarify → Scout → Establish → Review → Implement → Verify (+ Knowledge Deposition)
- **Multi-model orchestration** — Each phase assigned to the model with the strongest benchmark for that cognitive load
- **Isolated phase contexts** — Each phase runs in a fresh session with only the upstream contract (.md file), preventing context poisoning
- **Quality gates** — Each phase has mandatory fields; missing fields block progression
- **STATE_LOCKER protocol** — A state-machine prefix that forces the orchestrator to declare its phase, next action, and self-warning before every turn

## Files

| File | What |
|------|------|
| `CORE_CONCEPTS.md` | The what and why — state locker, pipeline, routing table |
| `PHASES.md` | Full detail of each phase — inputs, outputs, quality gates |
| `OT.md` | Orchestrator Threads — how to achieve true multi-model routing |
| `MODEL_ASSIGNMENT.md` | Which model for which phase, and why |
| `FAILURE_MODES.md` | Every known failure mode that shaped this framework |
| `APPENDIX.md` | Glossary, changelog, external references |
