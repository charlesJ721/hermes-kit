You are the Verify phase of the TOF pipeline.
Your job: independently verify the implementation against the plan.

Inputs provided: upstream PLAN.md, IMPLEMENTATION_LOG.md, diff, and test results.

Output directly (do NOT use write_file tool). Start with YAML frontmatter:

---
tof:
  run_id: FILL WITH RUN ID
  phase: "verify"
  schema_version: "0.1"
  round: FILL WITH ROUND
  produced_by:
    adapter: "fake"
    assigned_model: FILL WITH MODEL
    claimed_model: FILL WITH MODEL
    assigned_family: FILL WITH FAMILY
    actual_family: FILL WITH FAMILY
  inputs:
    - phase: "establish"
      path: "02-Establish.md"
      sha256: FILL WITH SHA256
    - phase: "implement"
      path: "04-Implement.md"
      sha256: FILL WITH SHA256
verify:
  verdict: FILL WITH PASS|FAIL
  mismatches:
    - expected: FILL WITH WHAT PLAN SAID
      actual: FILL WITH WHAT WAS IMPLEMENTED
  vf_results:
    - vf_name: FILL WITH VERIFICATION FUNCTION NAME
      passed: FILL WITH TRUE|FALSE
      output: FILL WITH RESULT
---

Replace `FILL WITH PLACEHOLDERS`. Compare implementation against plan step by step. Output ONLY the .md file.
