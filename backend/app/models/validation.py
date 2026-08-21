import uuid
from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, JSON, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

J = JSON().with_variant(JSONB(), 'postgresql')

class ValidationCase(Base):
    __tablename__ = 'validation_cases'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    source_text: Mapped[str] = mapped_column(Text, nullable=False)
    ground_truth: Mapped[dict] = mapped_column(J, nullable=False)
    module_targets: Mapped[list] = mapped_column(J, nullable=False, default=list)
    hazard_tags: Mapped[list] = mapped_column(J, nullable=False, default=list)
    difficulty: Mapped[str] = mapped_column(String(20), nullable=False, default='standard')
    version: Mapped[str] = mapped_column(String(30), nullable=False, default='1.0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

class ValidationRun(Base):
    __tablename__ = 'validation_runs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    validation_case_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('validation_cases.id'), nullable=False, index=True)
    organization_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    module: Mapped[str] = mapped_column(String(30), nullable=False, default='overview', index=True)
    scenario_injections: Mapped[list] = mapped_column(J, nullable=False, default=list)
    observed: Mapped[dict] = mapped_column(J, nullable=False)
    metrics: Mapped[dict] = mapped_column(J, nullable=False)
    physician_edit_ratio: Mapped[float | None] = mapped_column(Numeric)
    consequential_error_count: Mapped[int] = mapped_column(default=0)
    reviewer_scores: Mapped[dict] = mapped_column(J, nullable=False, default=dict)
    adjudication_status: Mapped[str] = mapped_column(String(30), nullable=False, default='unreviewed')
    adjudication_notes: Mapped[str | None] = mapped_column(Text)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='complete')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
