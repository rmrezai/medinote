from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FactCreate(BaseModel):
    source_document_id: UUID | None = None
    fact_type: str = Field(min_length=1, max_length=80)
    concept: str = Field(min_length=1, max_length=200)
    value_text: str | None = None
    value_numeric: float | None = None
    units: str | None = None
    evidence_text: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    observed_datetime: datetime | None = None
    source_datetime: datetime | None = None
    fact_state: str = "current"
    confidence: str = "high"
    source_category: str | None = None
    is_current: bool = True
    extracted_by: str | None = None
    extraction_version: str | None = None


class FactRead(FactCreate):
    id: UUID
    encounter_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


class ProblemCreate(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    normalized_name: str | None = None
    icd10_candidate: str | None = None
    certainty: str = "unclear"
    acuity_rank: int | None = None
    status: str = "active"
    parent_problem_id: UUID | None = None
    onset_datetime: datetime | None = None


class ProblemRead(ProblemCreate):
    id: UUID
    encounter_id: UUID
    physician_approved: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class ProblemEvidenceCreate(BaseModel):
    fact_id: UUID
    relationship: str | None = None
    evidence_strength: str | None = None


class MedicationCreate(BaseModel):
    normalized_name: str = Field(min_length=1, max_length=200)
    display_name: str | None = None
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None


class MedicationRead(MedicationCreate):
    id: UUID
    encounter_id: UUID
    created_at: datetime
    model_config = {"from_attributes": True}


class MedicationStateCreate(BaseModel):
    source_document_id: UUID | None = None
    domain: str
    status: str
    effective_datetime: datetime | None = None
    reason: str | None = None
    restart_criteria: str | None = None
    is_current: bool = True


class MedicationStateRead(MedicationStateCreate):
    id: UUID
    medication_id: UUID
    physician_confirmed: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class LabCreate(BaseModel):
    source_document_id: UUID | None = None
    test_name: str
    value_numeric: float | None = None
    value_text: str | None = None
    units: str | None = None
    reference_range: str | None = None
    abnormal_flag: str | None = None
    collection_datetime: datetime | None = None
    result_datetime: datetime | None = None


class VitalCreate(BaseModel):
    source_document_id: UUID | None = None
    vital_type: str
    value_numeric: float | None = None
    value_text: str | None = None
    units: str | None = None
    oxygen_device: str | None = None
    oxygen_flow_lpm: float | None = None
    observed_datetime: datetime | None = None


class ConsultantCreate(BaseModel):
    source_document_id: UUID | None = None
    service: str
    consultant_name: str | None = None
    recommendation_datetime: datetime | None = None
    assessment: str | None = None
    recommendation: str | None = None
    implementation_status: str | None = None
    current_relevance: str | None = None
    conflict_status: str | None = None


class PendingItemCreate(BaseModel):
    item_type: str
    description: str
    status: str = "pending"
    owner: str | None = None
    clinical_significance: str | None = None


class DispositionCreate(BaseModel):
    anticipated_destination: str | None = None
    current_barriers: list | dict | None = None
    mobility_status: str | None = None
    adl_status: str | None = None
    pt_recommendation: str | None = None
    ot_recommendation: str | None = None
    slp_recommendation: str | None = None
    oxygen_need: str | None = None
    equipment_need: str | None = None
    caregiver_support: str | None = None
    authorization_status: str | None = None
    transportation_status: str | None = None
    source_datetime: datetime | None = None


class ContradictionCreate(BaseModel):
    category: str
    fact_a_id: UUID | None = None
    fact_b_id: UUID | None = None
    description: str | None = None
    severity: str = "moderate"
    status: str = "unresolved"


class EncounterState(BaseModel):
    encounter_id: UUID
    facts: list[dict]
    problems: list[dict]
    medications: list[dict]
    labs: list[dict]
    vitals: list[dict]
    consultants: list[dict]
    pending_items: list[dict]
    disposition: dict | None
    contradictions: list[dict]


class ContradictionAdjudicateRequest(BaseModel):
    resolution_type: str = Field(pattern="^(select_source_a|select_source_b|new_clinical_decision)$")
    reason: str = Field(min_length=3)
    decision_text: str | None = None
    expected_revision: int | None = None


class ContradictionAdjudicateResponse(BaseModel):
    contradiction_id: UUID
    status: str
    physician_resolution: str
    resolution_type: str
    decision_fact_id: UUID | None = None
    affected_document_ids: list[UUID] = []
    regenerated_section_ids: list[UUID] = []
