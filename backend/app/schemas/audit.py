from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class SafetyFlagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    encounter_id: UUID
    document_id: UUID
    section_id: UUID | None = None
    category: str
    severity: str
    description: str
    claim_text: str | None = None
    supporting_evidence: list | dict | None = None
    status: str
    resolution: str | None = None
    created_at: datetime

class AuditResponse(BaseModel):
    document_id: UUID
    status: str
    blocking_flags: int = 0
    warning_flags: int = 0
    informational_flags: int = 0
    flags: list[SafetyFlagRead] = Field(default_factory=list)
    audit_version: str

class SafetyFlagResolveRequest(BaseModel):
    resolution: str
    actor_id: UUID | None = None
    resolution_type: str = "physician_reviewed"

class FinalizeRequest(BaseModel):
    actor_id: UUID | None = None
    expected_document_version: int | None = None

class FinalizeResponse(BaseModel):
    document_id: UUID
    status: str
    finalized_at: datetime | None = None
    blocking_flag_ids: list[UUID] = Field(default_factory=list)
