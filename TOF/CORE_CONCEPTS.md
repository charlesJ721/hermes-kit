# Core Concepts

## The Problem

A single LLM agent, given a multi-step task, will:

1. Assume it should do everything itself (it's an LLM — reasoning = acting)
2. Accumulate context over hours, diluting early decisions to noise
3. Never independently verify its own outputs
4. Let its model's blind spots compound across every phase

The result: what looks like a thorough pipeline is actually the same model talking to itself in different fonts.

## The Solution in One Diagram

```
N0: Clarify (Model A)
  ├── Input:  User request
  └── Output: TASK.md — scope, success criteria, exclusions
          ↓
N1: Scout (Model B)
  ├── Input:  TASK.md
  └── Output: RESEARCH.md — affected files, risks, unknowns
          ↓
N2: Establish (Model C)
  ├── Input:  TASK.md + RESEARCH.md
  └── Output: PLAN.md — design, steps, rollback
          ↓
N3: Review (Model D)
  ├── Input:  PLAN.md + RESEARCH.md
  └── Output: REVIEW.md — verdict, findings, blocking issues
          ↓
N4: Implement (Model C)
  ├── Input:  PLAN.md + REVIEW.md
  └── Output: Diff + tests + verification
          ↓
N5: Verify (Model A + D)
  ├── Input:  PLAN.md + diff + test results
  └── Output: VERIFICATION.md — PASS/FAIL per item
```

**Each node is an independent session.** No conversation history leaks between phases. Each node receives only the upstream .md file (2-5K tokens) plus its phase instructions (~2K tokens). Context window density ≥20% at all times.

## The Pipeline

### Standard SERI (for L2-L3 engineering tasks)

```
Clarify → Scout → Establish → Review → Implement → Verify
```

### Express Path (for L1 atomic tasks)

```
Clarify → Implement → Verify
```

### A-SRE (for pure analysis tasks)

```
Analyze → Adversarial Review → Synthesize
```

### Augmented SERI (for L3 + high-cost-failure tasks)

```
Clarify → Scout → Establish → RedTeam/BlueTeam Review → Implement → Verify
```

## Routing Table

Task classification uses three dimensions:

| Dimension | L1 (Atomic) | L2 (Module) | L3 (System) |
|-----------|-------------|-------------|-------------|
| Complexity | Single file change | 3+ file coordination | Cross-component architecture |
| Domain | Engineering / Analysis / Mixed | — | — |
| Cost of failure | Low (internal tool) | Medium (affects others) | High (architectural decision) |

```
L1 engineering + low cost       → Express path
L2 engineering + medium cost    → Standard SERI
L3 engineering + high cost      → Augmented SERI (Red/Blue team)
Pure analysis                   → A-SRE
Mixed                           → Serial (A-SRE first, then SERI implementation)
```

## STATE_LOCKER Protocol

For any L2/L3 task, every turn must begin with a state declaration:

```
[STATE_LOCKER]
- Task_Type: L2 / L3 / pure_analysis
- Current_Phase: [Phase N: Phase Name]
- Next_Action: [waiting_confirmation / dispatch_to → Model]
- Self_Warning: [current risk / constraint]
[/STATE_LOCKER]
```

**Enforcement:** If the orchestrator outputs code blocks (```python/```shell/```sql) without a preceding STATE_LOCKER block on an L2/L3 task, the output is treated as a core dump — the task is rolled back to Phase 0.

## Quality Gates (Mandatory Fields)

| Artifact | Required Fields | Missing → |
|----------|----------------|-----------|
| RESEARCH.md | `## affected_files`, `## unknowns` | BLOCKING |
| PLAN.md | `## steps`, `## rollback`, `## out_of_scope`, `## execution_mode` | BLOCKING |
| REVIEW.md | `review.verdict` (PASS/WEAKNESS_FOUND/BLOCKING) | BLOCKING |
| VERIFICATION.md | `verify.verdict` (PASS/FAIL) | BLOCKING |

**`unknowns` must be non-empty.** An empty unknowns array means Scout failed — it doesn't know what it doesn't know. Honest unknowns are a sign of good scouting.

## Orchestrator Behavior Boundaries

| Permitted | Prohibited |
|-----------|------------|
| Read upstream .md files | Depend on conversation memory >2 hours old |
| Write STATE_LOCKER + dispatch downstream | Override upstream .md conclusions with "conversation feel" |
| Write JUDGMENT.md (≤500 token decision summary) | Do the work assigned to downstream phases |

## Phase Archiving

Every phase's raw output is archived to a structured directory:

```
TOF Records/YYYY-MM-DD Task Name/
├── 00-Summary.md          ← Pipeline summary (written last)
├── 01-Scout-Model.md      ← Scout phase output
├── 02-Establish-Model.md  ← Establish phase output
├── 03-Review-Model.md     ← Review phase output
├── 04-Implement-Model.md  ← Implement phase output
└── 05-Verify-Model.md     ← Verify phase output
```

If a phase fails its quality gate and is retried, both versions are kept (`01-Scout-Model_v1.md`, `01-Scout-Model_v2.md`).
