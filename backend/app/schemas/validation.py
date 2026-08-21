from typing import Any
from uuid import UUID
from pydantic import BaseModel, Field

class ValidationCaseRead(BaseModel):
    id: UUID
    slug: str
    title: str
    category: str
    version: str
    source_text: str
    ground_truth: dict[str, Any]
    module_targets: list[str] = Field(default_factory=list)
    hazard_tags: list[str] = Field(default_factory=list)
    difficulty: str = 'standard'
    model_config = {'from_attributes': True}

class ValidationEvaluateRequest(BaseModel):
    observed: dict[str, Any]
    generated_text: str | None = None
    physician_final_text: str | None = None
    module: str = 'overview'
    scenario_injections: list[str] = Field(default_factory=list)
    reviewer_scores: dict[str, float] = Field(default_factory=dict)

class ValidationAdjudicateRequest(BaseModel):
    status: str
    notes: str | None = None
    reviewer_scores: dict[str, float] = Field(default_factory=dict)

class ValidationRunRead(BaseModel):
    id: UUID
    validation_case_id: UUID
    module: str
    scenario_injections: list[str]
    metrics: dict[str, Any]
    physician_edit_ratio: float | None
    consequential_error_count: int
    reviewer_scores: dict[str, Any]
    adjudication_status: str
    adjudication_notes: str | None
    passed: bool
    status: str
    model_config = {'from_attributes': True}

class ModuleSummary(BaseModel):
    module: str
    runs: int
    pass_rate: float
    consequential_errors: int
    mean_fact_precision: float
    mean_fact_recall: float
    mean_physician_edit_ratio: float

class ValidationDashboard(BaseModel):
    cases: int
    runs: int
    unique_cases_run: int
    adjudicated_runs: int
    mean_fact_precision: float
    mean_fact_recall: float
    mean_medication_accuracy: float
    mean_certainty_accuracy: float
    unsupported_claim_rate: float
    consequential_errors_per_100_cases: float
    mean_physician_edit_ratio: float
    module_summaries: list[ModuleSummary] = Field(default_factory=list)
    pilot_gate: str
    gate_reasons: list[str] = Field(default_factory=list)

class ValidationReport(BaseModel):
    study_name: str
    study_version: str
    generated_at: str
    dashboard: ValidationDashboard
    high_risk_failures: list[dict[str, Any]] = Field(default_factory=list)
    category_summary: list[dict[str, Any]] = Field(default_factory=list)
    report_markdown: str
