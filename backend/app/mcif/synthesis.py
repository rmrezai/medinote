from __future__ import annotations

from dataclasses import dataclass


SYNTHESIS_VERSION = "0.1.0"

# Conservative default ordering for documented active inpatient problems.
# Lower number means higher default synthesis priority. This is not a physician-approved acuity decision.
BASE_PRIORITY = {
    "acute_hypoxemic_respiratory_failure": 10,
    "sepsis": 20,
    "encephalopathy": 30,
    "gastrointestinal_bleeding": 35,
    "acute_kidney_injury": 40,
    "heart_failure": 50,
    "pneumonia": 60,
    "atrial_fibrillation": 70,
}

STATUS_OFFSET = {
    "worsening": -4,
    "new": -3,
    "active": 0,
    "under_evaluation": 1,
    "stable": 4,
    "improving": 8,
    "resolved": 1000,
}


@dataclass(frozen=True)
class ProblemSynthesis:
    status: str
    trajectory_basis: str | None = None
    evidence_concepts: tuple[str, ...] = ()


def synthesize_problem_status(normalized_name: str | None, trajectories: dict[tuple[str, str], str]) -> ProblemSynthesis:
    """Map objective descriptive trajectories onto an already documented problem.

    The function never creates a diagnosis and intentionally supports only relationships
    where the direction is clinically direct enough for an MVP rule. More nuanced
    interpretation belongs to a later physician-reviewed semantic layer.
    """
    name = normalized_name or ""

    if name == "acute_kidney_injury":
        trend = trajectories.get(("lab", "creatinine"))
        if trend == "falling":
            return ProblemSynthesis("improving", "creatinine_falling", ("creatinine",))
        if trend == "rising":
            return ProblemSynthesis("worsening", "creatinine_rising", ("creatinine",))
        if trend == "stable":
            return ProblemSynthesis("stable", "creatinine_stable", ("creatinine",))

    if name == "acute_hypoxemic_respiratory_failure":
        trend = trajectories.get(("respiratory_support", "oxygen_support"))
        if trend == "decreasing_support":
            return ProblemSynthesis("improving", "oxygen_support_decreasing", ("oxygen_flow", "oxygen_device"))
        if trend == "increasing_support":
            return ProblemSynthesis("worsening", "oxygen_support_increasing", ("oxygen_flow", "oxygen_device"))
        if trend == "stable":
            return ProblemSynthesis("stable", "oxygen_support_stable", ("oxygen_flow", "oxygen_device"))

    return ProblemSynthesis("active")


def acuity_rank(normalized_name: str | None, status: str) -> int:
    base = BASE_PRIORITY.get(normalized_name or "", 500)
    return max(1, base + STATUS_OFFSET.get(status, 0))
