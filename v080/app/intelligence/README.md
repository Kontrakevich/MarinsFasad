# System №1 Intelligence Pipeline v1

Native intelligence layer for MarinsFasad. It runs inside the existing application process; there is no second FastAPI service and no port 8092 dependency.

## Mandatory precedence

1. **Layer 1 — Technical / Execution Diagnostics** always runs first.
2. If Layer 1 finds a sufficient technical root cause (`root_cause_found=true`, confidence >= 0.70), its diagnosis is authoritative for this run. Human feedback is stored as evidence, but Layer 2 is **not invoked** and cannot override Layer 1.
3. **Layer 2 — Human / Logical Alignment** runs only when Layer 1 reports no sufficient technical root cause.
4. Repair Router produces a controlled repair route. It does not modify source code automatically.
5. Learning happens only after evidence and approval. An approval creates a regression reference; permanent BRAND/SYSTEM rules are never auto-promoted.

## Runtime flow

```text
MAIN PIPELINE
    |
    +--> RUN TRACE
    |
 RESULT / ERROR
    |
    v
LAYER 1: TECHNICAL LOCALIZER
    |
    +-- root cause found --> REPAIR ROUTER --> CONTROLLED RETRY
    |
    +-- no technical root cause
              |
              v
       LAYER 2: HUMAN ALIGNMENT
              |
              v
          REPAIR ROUTER
              |
              v
        CONTROLLED RETRY
              |
              v
        USER APPROVAL
              |
              v
   REGRESSION / LEARNING EVIDENCE
```

## Persistence

`<DATA_ROOT>/_system1/system1.sqlite3`

Tables:

- `runs`
- `events`
- `diagnoses`
- `feedback`
- `regression_cases`
- `preferences`

Secrets are redacted by key name before persistence.

## Current Layer 1 evidence

- provider / gateway failures;
- provider configuration failures;
- compiled-prompt transport mismatch;
- missing approved geometry;
- outpaint reconstruction failure / placeholder / incomplete coverage;
- deterministic quality-gate failure;
- generic runtime execution failure.

Generation trace also records the compiled-prompt SHA/length and selected engine-report fields such as generation mode, quality, provider-call count, outpaint refinement state and remaining missing pixels.

## Current Layer 2 taxonomy

- `INTENT_MISINTERPRETATION`
- `CONSTRAINT_DILUTION`
- `QUALITY_EXPECTATION_GAP`
- `OVERDESIGN`
- `STYLE_DRIFT`
- `BRAND_MISALIGNMENT`
- `POSITIVE_ALIGNMENT`

Layer 2 uses explicit user feedback only after the Layer 1 gate.

## Learning policy

- ordinary corrections are feedback evidence;
- approval creates an `APPROVED_REFERENCE` regression case;
- explicit phrases such as `всегда`, `никогда`, `правило`, `для MARINS` may create a **PROJECT CANDIDATE**;
- no automatic BRAND or SYSTEM promotion;
- no self-modifying source code.

## UI

Inspector tab `SYSTEM №1` shows:

- current run;
- Layer 1 diagnosis;
- Layer 2 status/diagnosis;
- repair route;
- regression/preference counts;
- recent Run Trace events.

## Next extension

Add a Visual Evidence Analyzer that compares approved geometry, generated result and internal missing-region evidence and reports measurable seam/detail/geometry deviations. It must feed Layer 1/Quality evidence first; subjective aesthetic interpretation remains Layer 2.
