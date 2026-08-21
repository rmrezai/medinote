from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.progress import ProgressEvidence


class DischargeGenerateRequest(BaseModel):
    variant: str = "summary"
    generated_by: UUID | None = None


class DischargeSection(BaseModel):
    id: UUID
    section_type: str
    section_key: str | None = None
    sort_order: int
    generated_content: str
    original_generated_content: str
    physician_content: str | None = None
    approval_status: str
    regeneration_count: int = 0
    problem_id: UUID | None = None
    evidence: list[ProgressEvidence] = Field(default_factory=list)


class DischargeDocumentResponse(BaseModel):
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
    sections: list[DischargeSection]
    review_required: bool
    review_reasons: list[str] = Field(default_factory=list)
