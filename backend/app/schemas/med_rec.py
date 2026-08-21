from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


ALLOWED_DISCHARGE_STATES = {
    "continue",
    "stop",
    "resume",
    "changed_dose",
    "changed_route",
    "changed_frequency",
    "newly_started",
    "inpatient_only",
    "completed",
    "unclear",
    "requires_decision",
}


class MedRecDecision(BaseModel):
    status: str = Field(min_length=1, max_length=50)
    reason: str | None = None
    restart_criteria: str | None = None
    effective_datetime: datetime | None = None
    confirmed_by: UUID | None = None
    expected_current_state_id: UUID | None = None


class MedRecStateSummary(BaseModel):
    state_id: UUID
    domain: str
    status: str
    reason: str | None = None
    restart_criteria: str | None = None
    effective_datetime: datetime | None = None
    physician_confirmed: bool
    revision: int = 1


class MedRecMedicationSummary(BaseModel):
    medication_id: UUID
    name: str
    normalized_name: str
    dose: str | None = None
    route: str | None = None
    frequency: str | None = None
    indication: str | None = None
    home: MedRecStateSummary | None = None
    hospital: MedRecStateSummary | None = None
    discharge: MedRecStateSummary | None = None
    unresolved: bool
    high_risk: bool
    transition_summary: str


class MedRecWorkspace(BaseModel):
    encounter_id: UUID
    medications: list[MedRecMedicationSummary]
    unresolved_count: int
    high_risk_count: int
    changed_count: int
