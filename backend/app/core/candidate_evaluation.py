"""Candidate evaluation planning for MediNote IQ regenerative learning.

Recurring learning patterns may automatically create a reviewable candidate
scaffold and evaluation plan. This module does not rewrite clinical rules,
generate executable changes, mutate charts, train/deploy models, or promote
anything automatically.
"""
from dataclasses import dataclass

from app.core.regenerative_learning import ImprovementCandidate


CANDIDATE_EVALUATION_VERSION = "medinote-candidate-evaluation-v1"

_BASE_SUITES = (
    "golden-case",
    "chart-torture",
    "full-regression",
    "clinical-safety",
)

_MODULE_EXTRA_SUITES = {
    "coding": ("coding-cdi",),
    "cdi": ("coding-cdi",),
    "med_rec": ("medication-state",),
    "discharge": ("discharge-safety",),
    "signout": ("signout-safety",),
    "safety": ("safety-audit",),
}


class CandidateEvaluationError(ValueError):
    pass


@dataclass(frozen=True)
class EvaluationPlan:
    candidate_ref: str
    module: str
    required_suites: tuple[str, ...]
    baseline_ref: str
    evaluation_set_ref: str
    human_review_required: bool = True
    auto_deploy_allowed: bool = False
    production_mutation_allowed: bool = False
    version: str = CANDIDATE_EVALUATION_VERSION


@dataclass(frozen=True)
class SuiteResult:
    suite: str
    passed: bool
    baseline_score: float | None = None
    candidate_score: float | None = None
    lower_is_better: bool = False


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate_ref: str
    passed: bool
    reason: str
    suite_results: tuple[SuiteResult, ...]
    improved_or_equal: bool
    review_queue_status: str = "awaiting-human-approval"
    automatic_promotion_allowed: bool = False
    production_mutation_performed: bool = False
    version: str = CANDIDATE_EVALUATION_VERSION


def build_evaluation_plan(candidate, *, baseline_ref, evaluation_set_ref):
    if not isinstance(candidate, ImprovementCandidate):
        raise CandidateEvaluationError("invalid-candidate")
    if not isinstance(baseline_ref, str) or not baseline_ref.strip():
        raise CandidateEvaluationError("baseline-required")
    if not isinstance(evaluation_set_ref, str) or not evaluation_set_ref.strip():
        raise CandidateEvaluationError("evaluation-set-required")
    required = _BASE_SUITES + _MODULE_EXTRA_SUITES.get(candidate.module, ())
    return EvaluationPlan(
        candidate_ref=candidate.candidate_ref,
        module=candidate.module,
        required_suites=required,
        baseline_ref=baseline_ref.strip(),
        evaluation_set_ref=evaluation_set_ref.strip(),
    )


def evaluate_candidate(plan, suite_results):
    """Evaluate supplied evidence and fail closed on missing/regressed suites.

    Suite execution occurs in validated test/evaluation workers. This function
    only checks the resulting evidence and can never deploy the candidate.
    """
    if not isinstance(plan, EvaluationPlan):
        raise CandidateEvaluationError("invalid-plan")
    if not isinstance(suite_results, tuple):
        raise CandidateEvaluationError("invalid-suite-results")
    if any(not isinstance(item, SuiteResult) for item in suite_results):
        raise CandidateEvaluationError("invalid-suite-result")

    by_name = {item.suite: item for item in suite_results}
    if len(by_name) != len(suite_results):
        raise CandidateEvaluationError("duplicate-suite-result")

    missing = tuple(name for name in plan.required_suites if name not in by_name)
    if missing:
        return CandidateEvaluation(
            candidate_ref=plan.candidate_ref,
            passed=False,
            reason="required-suite-missing:" + ",".join(missing),
            suite_results=suite_results,
            improved_or_equal=False,
            review_queue_status="blocked",
        )

    required = tuple(by_name[name] for name in plan.required_suites)
    failed = tuple(item.suite for item in required if item.passed is not True)
    if failed:
        return CandidateEvaluation(
            candidate_ref=plan.candidate_ref,
            passed=False,
            reason="suite-failed:" + ",".join(failed),
            suite_results=required,
            improved_or_equal=False,
            review_queue_status="blocked",
        )

    improved_or_equal = True
    for item in required:
        if item.baseline_score is None or item.candidate_score is None:
            continue
        if item.lower_is_better:
            improved_or_equal = improved_or_equal and item.candidate_score <= item.baseline_score
        else:
            improved_or_equal = improved_or_equal and item.candidate_score >= item.baseline_score

    if not improved_or_equal:
        return CandidateEvaluation(
            candidate_ref=plan.candidate_ref,
            passed=False,
            reason="baseline-regression",
            suite_results=required,
            improved_or_equal=False,
            review_queue_status="blocked",
        )

    return CandidateEvaluation(
        candidate_ref=plan.candidate_ref,
        passed=True,
        reason="evaluation-passed-human-review-required",
        suite_results=required,
        improved_or_equal=True,
    )


__all__ = [
    "CANDIDATE_EVALUATION_VERSION",
    "CandidateEvaluationError",
    "EvaluationPlan",
    "SuiteResult",
    "CandidateEvaluation",
    "build_evaluation_plan",
    "evaluate_candidate",
]
