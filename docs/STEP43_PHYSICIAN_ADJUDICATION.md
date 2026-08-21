# MediNote Step 43 — Physician Adjudication of Contradictions

## Objective
Provide a physician-controlled workflow for resolving contradictions without deleting source history or silently choosing a clinical interpretation.

## Workflow
1. MediNote detects and preserves a contradiction.
2. The physician opens the contradiction and sees Source A and Source B when available.
3. The physician chooses Source A, Source B, or records a new clinical decision.
4. The physician documents the reason for adjudication.
5. MediNote creates a physician-adjudication fact with provenance.
6. The contradiction is marked resolved while both original sources remain stored.
7. When applicable, the adjudication updates current structured state (for example current oxygen state or a physician-confirmed hospital medication state).
8. Existing draft/in-review Progress and Signout sections are regenerated from the updated MCIF state.
9. Those documents are automatically re-audited.
10. Sections must still be physician reviewed/accepted before approval and finalization.

## API
- `GET /api/v1/contradictions/{contradiction_id}`
- `POST /api/v1/contradictions/{contradiction_id}/adjudicate`

Example request:

```json
{
  "resolution_type": "select_source_b",
  "reason": "Current bedside nursing documentation is the most reliable same-time oxygen source.",
  "decision_text": null
}
```

Valid `resolution_type` values:
- `select_source_a`
- `select_source_b`
- `new_clinical_decision`

`new_clinical_decision` requires `decision_text`.

## Safety behavior
- Original conflicting evidence is not deleted.
- The physician decision is stored separately from source facts.
- A consultant recommendation does not become an implemented medication state until physician adjudication explicitly selects/adopts it.
- A selected medication recommendation can create a physician-confirmed hospital medication state when the action can be parsed conservatively.
- Finalization remains governed by section review plus the existing Safety Audit.
- Adjudication does not bypass unrelated safety flags.

## Step 43 torture-case result
The Step 42 oxygen and consultant conflicts were adjudicated in an automated end-to-end test:
- same-time oxygen conflict resolved to current room-air state;
- Nephrology hold recommendation selected by the treating physician;
- furosemide became a physician-confirmed hospital `held` state;
- Progress and Signout sections regenerated;
- unresolved contradiction audit flags cleared;
- both documents could be re-reviewed, approved, audited, and finalized.

## Validation
Full regression suite: 86/86 tests passed.
Frontend JavaScript syntax check: passed.
