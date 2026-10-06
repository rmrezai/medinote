from app.core import regenerative_learning as rli


def signal(**overrides):
    values = dict(
        signal_ref="sig-001",
        signal_type="physician-edit",
        module="progress",
        disposition="edited",
        source_ref="run-001",
        artifact_version_ref="progress-v1",
        reviewer_role="attending",
        reason_code="unsupported-claim-corrected",
        consequential_error_count=0,
        physician_edit_ratio=0.12,
    )
    values.update(overrides)
    return rli.build_learning_signal(**values)


def test_learning_signal_contains_no_raw_clinical_content():
    item = signal()
    assert item.synthetic_or_deidentified is True
    assert item.contains_raw_clinical_text is False
    assert item.contains_direct_identifier is False


def test_validation_summary_becomes_structured_learning_signal():
    item = rli.validation_signal(
        run_ref="run-002",
        module="discharge",
        adjudication_status="rejected",
        artifact_version_ref="discharge-v4",
        reviewer_role="attending",
        reason_code="medication-state-error",
        consequential_error_count=1,
        physician_edit_ratio=0.25,
    )
    assert item.signal_type == "validation-failure"
    assert item.disposition == "rejected"
    assert item.consequential_error_count == 1


def test_improvement_candidate_never_auto_applies():
    candidate = rli.propose_improvement(
        candidate_ref="cand-001",
        module="progress",
        change_kind="validation-case",
        source_signals=(signal(),),
        target_artifact_ref="progress-validation",
        target_version_ref="v2",
    )
    assert candidate.auto_apply is False
    assert candidate.production_mutation_allowed is False


def test_cross_module_feedback_requires_explicit_design():
    other = signal(
        signal_ref="sig-002",
        module="discharge",
        artifact_version_ref="discharge-v1",
    )
    try:
        rli.propose_improvement(
            candidate_ref="cand-002",
            module="progress",
            change_kind="prompt",
            source_signals=(signal(), other),
            target_artifact_ref="progress-prompt",
            target_version_ref="v2",
        )
    except rli.RegenerativeLearningError as exc:
        assert str(exc) == "cross-module-candidate-requires-explicit-design"
    else:
        raise AssertionError("expected fail-closed cross-module candidate")


def test_promotion_requires_validation_physician_and_owner_approval():
    candidate = rli.propose_improvement(
        candidate_ref="cand-003",
        module="progress",
        change_kind="deterministic-rule",
        source_signals=(signal(),),
        target_artifact_ref="progress-rule",
        target_version_ref="v2",
    )
    evidence = rli.PromotionEvidence(
        golden_set_passed=True,
        torture_set_passed=True,
        regression_passed=True,
        safety_review_passed=True,
        physician_adjudication_complete=True,
        clinical_owner_approved=True,
        technical_owner_approved=True,
        regulatory_review_passed=False,
        evaluation_set_ref="eval-v2",
        rollback_target_ref="release-v1",
    )
    decision = rli.evaluate_promotion(candidate, evidence)
    assert decision.eligible_for_reviewed_release is True
    assert decision.automatic_promotion_allowed is False
    assert decision.production_mutation_performed is False


def test_intended_use_change_requires_regulatory_review():
    candidate = rli.propose_improvement(
        candidate_ref="cand-004",
        module="safety",
        change_kind="safety-check",
        source_signals=(
            signal(
                signal_ref="sig-004",
                module="safety",
                signal_type="safety-flag-resolution",
                disposition="resolved",
                artifact_version_ref="safety-v1",
                reason_code="false-positive",
            ),
        ),
        target_artifact_ref="safety-policy",
        target_version_ref="v2",
        intended_use_changed=True,
    )
    evidence = rli.PromotionEvidence(
        golden_set_passed=True,
        torture_set_passed=True,
        regression_passed=True,
        safety_review_passed=True,
        physician_adjudication_complete=True,
        clinical_owner_approved=True,
        technical_owner_approved=True,
        regulatory_review_passed=False,
        evaluation_set_ref="eval-v2",
        rollback_target_ref="release-v1",
    )
    decision = rli.evaluate_promotion(candidate, evidence)
    assert decision.eligible_for_reviewed_release is False
    assert decision.reason == "regulatory-review-required"
