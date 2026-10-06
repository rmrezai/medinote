import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


J = JSON().with_variant(JSONB(), "postgresql")


class LearningSignalRecord(Base):
    __tablename__ = "learning_signal_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "signal_ref", name="uq_learning_signal_org_ref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    signal_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    disposition: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    artifact_version_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    reviewer_role: Mapped[str] = mapped_column(String(80), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    consequential_error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    physician_edit_ratio: Mapped[float | None] = mapped_column()
    synthetic_or_deidentified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    contains_raw_clinical_text: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    contains_direct_identifier: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metadata_json: Mapped[dict] = mapped_column(J, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LearningPatternRecord(Base):
    __tablename__ = "learning_pattern_records"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "module",
            "reason_code",
            "source_artifact_version_ref",
            name="uq_learning_pattern_scope",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    module: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    source_artifact_version_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    occurrences: Mapped[int] = mapped_column(Integer, nullable=False)
    dispositions: Mapped[dict] = mapped_column(J, nullable=False, default=dict)
    signal_refs: Mapped[list] = mapped_column(J, nullable=False, default=list)
    ready_for_candidate_review: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
