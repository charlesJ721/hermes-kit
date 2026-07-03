# hermes-kit

> A curated collection of agent orchestration patterns, framework designs, and operational recipes — extracted from real Hermes Agent deployments and battle-tested in daily use.

**hermes-kit** is a monorepo of practical, shareable artifacts for anyone running AI agents at the CLI/shell level. Each module is self-contained, provider-agnostic where possible, and annotated with the failures that shaped it.

## Contents

| Module | What | For whom |
|--------|------|----------|
| **TOF/** | Task Orchestration Framework — multi-model pipeline with five phases, three verification layers, and a state-machine protocol that prevents agent drift | Anyone running a non-trivial multi-turn agent workflow |
| *(more coming)* | | |

## Design Principles

These aren't aspirations — they're binding constraints that survive across every module in this repo:

1. **Concrete over aspirational.** Every pattern here was discovered by fixing a real failure, not by reasoning from first principles. The failure is documented alongside the fix.
2. **Auditable over efficient.** An unverifiable pipeline is a fake pipeline. Every model dispatch, every delegation, every claim about what an agent actually did — must leave a trace that can be checked independently.
3. **Who before how.** Before deciding how to execute a task, decide who should execute it. Defaulting to "I'll do it" is the single most expensive bias in agent orchestration.
4. **Modular models.** No single model should be the bottleneck. Design the orchestration so each phase can use the model best suited for that cognitive load, and swap models without redesigning the pipeline.

## License

MIT — take what's useful, leave what isn't. Attribution appreciated but not required.
