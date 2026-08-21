import uuid
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, event, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

JsonType = JSON().with_variant(JSONB, 'postgresql')


class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditEvent(Base):
    __tablename__ = 'audit_events'
    __table_args__ = (UniqueConstraint('organization_id','sequence_number',name='uq_audit_org_sequence'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('encounters.id'), index=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    object_type: Mapped[str | None] = mapped_column(String(80))
    object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    metadata_json: Mapped[dict | None] = mapped_column(JsonType)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=False, default='0' * 64)
    metadata_hash: Mapped[str] = mapped_column(String(64), nullable=False, default='')
    event_hash: Mapped[str] = mapped_column(String(64), nullable=False, default='', unique=True, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)


class EditLease(Base):
    __tablename__ = 'edit_leases'
    __table_args__ = (UniqueConstraint('organization_id','resource_type','resource_id',name='uq_edit_lease_resource'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('encounters.id'), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    refreshed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class IdempotencyReceipt(Base):
    __tablename__ = 'idempotency_receipts'
    __table_args__ = (UniqueConstraint('organization_id','user_id','idempotency_key',name='uq_idempotency_user_key'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False)
    method: Mapped[str] = mapped_column(String(12), nullable=False)
    path: Mapped[str] = mapped_column(String(300), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='in_progress', index=True)
    response_json: Mapped[dict | list | None] = mapped_column(JsonType)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


def _immutable_audit_event(*args, **kwargs):
    raise ValueError('AuditEvent rows are append-only and cannot be updated or deleted')

event.listen(AuditEvent, 'before_update', _immutable_audit_event)
event.listen(AuditEvent, 'before_delete', _immutable_audit_event)

class AuditAnchor(Base):
    __tablename__ = 'audit_anchors'
    __table_args__ = (UniqueConstraint('organization_id','sequence_number',name='uq_anchor_org_sequence'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_event_count: Mapped[int] = mapped_column(Integer, nullable=False)
    audit_head_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class LegalHold(Base):
    __tablename__ = 'legal_holds'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('encounters.id'), index=True)
    matter_reference: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='active', index=True)
    placed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'), nullable=False)
    placed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    released_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    release_reason: Mapped[str | None] = mapped_column(Text)


class RetentionSnapshot(Base):
    __tablename__ = 'retention_snapshots'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('organizations.id'), nullable=False, index=True)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey('encounters.id'), nullable=False, index=True)
    format_version: Mapped[str] = mapped_column(String(50), nullable=False, default='medinote-retention-v0.1')
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    storage_uri: Mapped[str] = mapped_column(String(500), nullable=False)
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    legal_hold_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
