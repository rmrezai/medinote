from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EvidenceItem(BaseModel):
    fact_id: UUID
    concept: str
    value: str | None = None
    units: str | None = None
    observed_datetime: datetime | None = None
    confidence: str | None = None
    source_document_id: UUID | None = None
    relationship: str | None = None
    evidence_strength: str | None = None


class OverviewProblem(BaseModel):
    id: UUID
    name: str
    normalized_name: str | None = None
    certainty: str
    status: str
    acuity_rank: int | None = None
    physician_approved: bool
    evidence: list[EvidenceItem] = []


class LatestLab(BaseModel):
    id: UUID
    test_name: str
    value_numeric: float | None = None
    value_text: str | None = None
    units: str | None = None
    abnormal_flag: str | None = None
    collection_datetime: datetime | None = None
    trend: str | None = None
    earliest_value: str | None = None
    latest_value: str | None = None


class MedicationStateSummary(BaseModel):
    domain: str
    status: str
    effective_datetime: datetime | None = None
    reason: str | None = None
    restart_criteria: str | None = None
    physician_confirmed: bool


class OverviewMedication(BaseModel):
    id: UUID
    name: str
    normalized_name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None
    states: list[MedicationStateSummary] = []
    unresolved: bool = False


class OverviewConsultant(BaseModel):
    id: UUID
    service: str
    consultant_name: str | None = None
    recommendation_datetime: datetime | None = None
    assessment: str | None = None
    recommendation: str | None = None
    implementation_status: str | None = None
    conflict_status: str | None = None


class OverviewPendingItem(BaseModel):
    id: UUID
    item_type: str
    description: str
    status: str
    owner: str | None = None
    clinical_significance: str | None = None


class OverviewDisposition(BaseModel):
    anticipated_destination: str | None = None
    current_barriers: list | dict | None = None
    mobility_status: str | None = None
    pt_recommendation: str | None = None
    ot_recommendation: str | None = None
    slp_recommendation: str | None = None
    oxygen_need: str | None = None
    authorization_status: str | None = None


class OverviewContradiction(BaseModel):
    id: UUID
    category: str
    description: str | None = None
    severity: str
    status: str
    fact_a_id: UUID | None = None
    fact_b_id: UUID | None = None


class PatientOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    encounter_id: UUID
    patient_id: UUID
    patient_display_name: str | None = None
    mrn: str | None = None
    service: str | None = None
    location: str | None = None
    admission_datetime: datetime | None = None
    encounter_status: str
    current_clinical_picture: str
    problems: list[OverviewProblem]
    latest_labs: list[LatestLab]
    medications: list[OverviewMedication]
    consultants: list[OverviewConsultant]
    pending_items: list[OverviewPendingItem]
    disposition: OverviewDisposition | None = None
    contradictions: list[OverviewContradiction]
    attention_counts: dict[str, int]
