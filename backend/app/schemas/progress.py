from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, ConfigDict


class ProgressGenerateRequest(BaseModel):
    variant: str = "daily"
    generated_by: UUID | None = None


class ProgressEvidence(BaseModel):
    fact_id: UUID
    concept: str
    value: str | None = None
    observed_datetime: datetime | None = None
    source_document_id: UUID | None = None


class ProgressSection(BaseModel):
    id: UUID
    section_type: str
    section_key: str | None = None
    sort_order: int
    generated_content: str
    original_generated_content: str
    physician_content: str | None = None
    approval_status: str
    regeneration_count: int = 0
    edit_version: int = 1
    problem_id: UUID | None = None
    evidence: list[ProgressEvidence] = Field(default_factory=list)


class ProgressDocumentResponse(BaseModel):
    document_id: UUID
    encounter_id: UUID
    document_type: str
    variant: str
    status: str
    generator_version: str
    generated_at: datetime
    approved_at: datetime | None = None
    generated_state_version: int = 1
    current_state_version: int = 1
    stale: bool = False
    edit_version: int = 1
    sections: list[ProgressSection]
    review_required: bool
    review_reasons: list[str] = Field(default_factory=list)


class ProgressSectionUpdate(BaseModel):
    physician_content: str | None = None
    action: str = "edit"  # edit | accept
    actor_id: UUID | None = None
    expected_section_version: int | None = None
    expected_document_version: int | None = None


class ProgressSectionRegenerateRequest(BaseModel):
    instruction: str | None = None
    actor_id: UUID | None = None
    expected_section_version: int | None = None
    expected_document_version: int | None = None


class DocumentApproveRequest(BaseModel):
    actor_id: UUID | None = None
    expected_document_version: int | None = None


class DocumentApprovalResponse(BaseModel):
    document_id: UUID
    status: str
    approved_at: datetime | None = None
    generated_state_version: int = 1
    current_state_version: int = 1
    stale: bool = False
    edit_version: int = 1
    pending_section_ids: list[UUID] = Field(default_factory=list)


class PhysicianEditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    document_id: UUID
    section_id: UUID
    action: str
    original_generated_content: str
    active_generated_content: str
    prior_physician_content: str | None = None
    final_physician_content: str | None = None
    instruction: str | None = None
    edited_by: UUID | None = None
    edited_at: datetime
