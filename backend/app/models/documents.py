import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClinicalDocument(Base):
    __tablename__ = "clinical_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    variant: Mapped[str | None] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False, default="progress-deterministic-v0.1")
    generated_state_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    generated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DocumentSection(Base):
    __tablename__ = "document_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_documents.id"), nullable=False, index=True)
    section_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    section_key: Mapped[str | None] = mapped_column(String(120), index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    # Immutable first-generation text. Never overwrite this field.
    generated_content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # Most recent regenerated draft, if regeneration has occurred.
    current_generated_content: Mapped[str | None] = mapped_column(Text)
    physician_content: Mapped[str | None] = mapped_column(Text)
    approval_status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    regeneration_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edit_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SectionRevision(Base):
    __tablename__ = "section_revisions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_documents.id"), nullable=False, index=True)
    section_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_sections.id"), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    instruction: Mapped[str | None] = mapped_column(Text)
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PhysicianEdit(Base):
    __tablename__ = "physician_edits"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_documents.id"), nullable=False, index=True)
    section_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("document_sections.id"), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(30), nullable=False)  # edit | accept | regenerate | approve
    original_generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    active_generated_content: Mapped[str] = mapped_column(Text, nullable=False)
    prior_physician_content: Mapped[str | None] = mapped_column(Text)
    final_physician_content: Mapped[str | None] = mapped_column(Text)
    instruction: Mapped[str | None] = mapped_column(Text)
    edited_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    edited_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
