import unittest

from app.core import regenerative_learning as rli


class RegenerativeLearningTests(unittest.TestCase):
    def signal(self, **overrides):
        values = dict(
            signal_ref="sig-001",
            signal_type="physician-edit",
            module="progress",
            disposition="edited",
            source_ref="validation-run-001",
            artifact_version_ref="progress-v1",
            reviewer_role="attending",
            reason_code="factual-correction",
            consequential_error_count=0,
            physician_edit_ratio=0.12,
        )
        values.update(overrides)
        return rli.build_learning_signal(**values)

    def test_learning_signal_is_safe_metadata_only(self):
        signal = self.signal()
        self.assertTrue(signal.synthetic_or_deidentified)
        self.assertFalse(signal.contains_raw_clinical_text)
        self.assertFalse(signal.contains_direct_identifier)

    def test_validation_summary_can_become_learning_signal(self):
        signal = rli.validation_signal(
            run_ref="run-002",
            module="discharge",
            adjudication_status="rejected",
            artifact_version_ref="discharge-v3",
            reviewer_role="attending",
            reason_code="medication-state-error",
            consequential_error_count=1,
            physician_edit_ratio=0.25,
        )
        self.assertEqual(signal.signal_type, "validation-failure")
        self.assertEqual(signal.disposition, "rejected")
        self.assertEqual(signal.consequential_error_count, 1)

    def test_candidate_never_auto_applies(self):
        candidate = rli.propose_improvement(
            candidate_ref="cand-001",
            module="progress",
            change_kind="deterministic-rule",
            source_signals=(self.signal(),),
            target_artifact_ref="progress-generator",
            target_version_ref="v2",
        )
        self.assertFalse(candidate.auto_apply)
        self.assertFalse(candidate.production_mutation_allowed)

    def test_cross_module_learning_requires_explicit_design(self):
        other = self.signal(
            signal_ref="sig-002",
            module="coding",
            signal_type="coding-correction",
            reason_code="specificity-correction",
        )
        with self.assertRaisesRegex(
            rli.RegenerativeLearningError,
            "cross-module-candidate-requires-explicit-design",
        ):
            rli.propose_improvement(
                candidate_ref="cand-002",
                module="progress",
                change_kind="prompt",
                source_signals=(self.signal(), other),
                target_artifact_ref="progress-prompt",
                target_version_ref="v2",
            )

    def test_promotion_requires_full_validation_and_human_approval(self):
        candidate = rli.propose_improvement(
            candidate_ref="cand-003",
            module="safety",
            change_kind="safety-check",
            source_signals=(
                self.signal(
                    signal_ref="sig-003",
                    module="safety",
                    signal_type="safety-flag-resolution",
                    disposition="resolved",
                    reason_code="false-positive",
                ),
            ),
            target_artifact_ref="safety-audit",
            target_version_ref="v4",
        )
        blocked = rli.evaluate_promotion(
            candidate,
            rli.PromotionEvidence(
                golden_set_passed=True,
                torture_set_passed=True,
                regression_passed=True,
                safety_review_passed=True,
                physician_adjudication_complete=True,
                clinical_owner_approved=False,
                technical_owner_approved=True,
                regulatory_review_passed=True,
                evaluation_set_ref="eval-v4",
                rollback_target_ref="release-v3",
            ),
        )
        self.assertFalse(blocked.eligible_for_reviewed_release)
        self.assertEqual(blocked.reason, "clinical-owner-approval-required")

        approved = rli.evaluate_promotion(
            candidate,
            rli.PromotionEvidence(
                golden_set_passed=True,
                torture_set_passed=True,
                regression_passed=True,
                safety_review_passed=True,
                physician_adjudication_complete=True,
                clinical_owner_approved=True,
                technical_owner_approved=True,
                regulatory_review_passed=True,
                evaluation_set_ref="eval-v4",
                rollback_target_ref="release-v3",
            ),
        )
        self.assertTrue(approved.eligible_for_reviewed_release)
        self.assertFalse(approved.automatic_promotion_allowed)
        self.assertFalse(approved.production_mutation_performed)

    def test_intended_use_change_requires_regulatory_review(self):
        candidate = rli.propose_improvement(
            candidate_ref="cand-004",
            module="cdi",
            change_kind="prompt",
            source_signals=(
                self.signal(
                    signal_ref="sig-004",
                    module="cdi",
                    signal_type="cdi-correction",
                    reason_code="clarity-correction",
                ),
            ),
            target_artifact_ref="cdi-prompt",
            target_version_ref="v5",
            intended_use_changed=True,
        )
        decision = rli.evaluate_promotion(
            candidate,
            rli.PromotionEvidence(
                golden_set_passed=True,
                torture_set_passed=True,
                regression_passed=True,
                safety_review_passed=True,
                physician_adjudication_complete=True,
                clinical_owner_approved=True,
                technical_owner_approved=True,
                regulatory_review_passed=False,
                evaluation_set_ref="eval-v5",
                rollback_target_ref="release-v4",
            ),
        )
        self.assertFalse(decision.eligible_for_reviewed_release)
        self.assertEqual(decision.reason, "regulatory-review-required")

    def test_longitudinal_modules_are_separate_learning_domains(self):
        cases = (
            ("medication-profile", "medication-reconciliation-correction"),
            ("allergy-profile", "allergy-reconciliation-correction"),
            ("external-ehr", "external-record-reconciliation"),
            ("laboratory", "lab-result-followup-correction"),
            ("radiology", "radiology-followup-correction"),
            ("referral", "referral-followup-correction"),
            ("longitudinal-record", "history-reconciliation-correction"),
        )
        signals = []
        for index, (module, signal_type) in enumerate(cases, start=20):
            signals.append(
                self.signal(
                    signal_ref=f"sig-{index}",
                    module=module,
                    signal_type=signal_type,
                    reason_code=f"{module}-correction",
                )
            )
        self.assertEqual({x.module for x in signals}, {x[0] for x in cases})

    def test_longitudinal_improvements_remain_non_mutating(self):
        signal = self.signal(
            signal_ref="sig-90",
            module="allergy-profile",
            signal_type="allergy-reconciliation-correction",
            reason_code="source-mismatch",
        )
        candidate = rli.propose_improvement(
            candidate_ref="cand-90",
            module="allergy-profile",
            change_kind="reconciliation-rule",
            source_signals=(signal,),
            target_artifact_ref="allergy-reconciliation",
            target_version_ref="v1",
        )
        self.assertFalse(candidate.auto_apply)
        self.assertFalse(candidate.production_mutation_allowed)


if __name__ == "__main__":
    unittest.main()
