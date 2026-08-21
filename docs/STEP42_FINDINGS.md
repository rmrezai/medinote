# MediNote Step 42 — Findings and Fixes

## Final result
- 10/10 torture-state assertions passed.
- 84/84 automated regression tests passed.
- Progress and Signout remain review-required because two deliberately unresolved contradictions remain visible for physician adjudication.

## Defects exposed and corrected
1. **Source-authority mismatch** — nursing documentation had been ranked below ordinary clinician narrative at equal timestamps. The hierarchy now matches MediNote governance more closely: objective > consultant > nursing > clinician narrative for the currently modeled categories.
2. **Ruled-out diagnosis resurrection** — a later copied-forward bare diagnosis could recreate a diagnosis after it had been explicitly ruled out. A conservative resolved/ruled-out tombstone now prevents silent resurrection from bare copied text.
3. **Duplicate medication identity** — dose-bearing home-med strings such as `losartan 50 mg daily` could become a separate medication from `losartan`. Normalization now strips trailing dose/frequency fragments for the currently supported deterministic pattern.
4. **Procedure lifecycle regression** — procedure state was not extracted. Planned/pending/cancelled/completed states are now structured, and a terminal cancelled/completed state does not regress to stale planned text.
5. **Consultant recommendation conflation** — consultant recommendations with action verbs could be incorrectly parsed as implemented medication states. Consultant source text now remains recommendation-only unless implementation is documented elsewhere.
6. **Consultant conflict invisibility** — explicit opposing recommendations for the same medication are now preserved as a consultant-recommendation contradiction rather than silently collapsed.
7. **Amended final result parsing** — `amended final` result language now resolves matching pending items.

## Deliberately unresolved at the end of the torture case
- Cardiology says continue furosemide while Nephrology says hold furosemide.
- Same-time clinician copied-forward oxygen state conflicts with nursing room-air documentation; current-state selection follows source authority, but the disagreement remains auditable.

These unresolved conflicts are expected safety behavior, not test failures.
