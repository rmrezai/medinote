import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ClinicalFact(Base):
    __tablename__ = "clinical_facts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"), index=True)
    fact_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    value_text: Mapped[str | None] = mapped_column(Text)
    value_numeric: Mapped[float | None] = mapped_column(Numeric)
    units: Mapped[str | None] = mapped_column(String(80))
    evidence_text: Mapped[str | None] = mapped_column(Text)
    source_start: Mapped[int | None] = mapped_column(Integer)
    source_end: Mapped[int | None] = mapped_column(Integer)
    observed_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fact_state: Mapped[str] = mapped_column(String(40), nullable=False, default="current", index=True)
    confidence: Mapped[str] = mapped_column(String(30), nullable=False, default="high")
    source_category: Mapped[str | None] = mapped_column(String(50))
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_facts.id"))
    extracted_by: Mapped[str | None] = mapped_column(String(100))
    extraction_version: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicalProblem(Base):
    __tablename__ = "clinical_problems"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str | None] = mapped_column(String(300), index=True)
    icd10_candidate: Mapped[str | None] = mapped_column(String(30))
    certainty: Mapped[str] = mapped_column(String(40), nullable=False, default="unclear")
    acuity_rank: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="active", index=True)
    parent_problem_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_problems.id"))
    onset_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    resolved_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    physician_approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ProblemEvidence(Base):
    __tablename__ = "problem_evidence"
    __table_args__ = (UniqueConstraint("problem_id", "fact_id", name="uq_problem_fact_evidence"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    problem_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_problems.id"), nullable=False, index=True)
    fact_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_facts.id"), nullable=False, index=True)
    relationship: Mapped[str | None] = mapped_column(String(100))
    evidence_strength: Mapped[str | None] = mapped_column(String(30))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Medication(Base):
    __tablename__ = "medications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    normalized_name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200))
    dose: Mapped[str | None] = mapped_column(String(100))
    route: Mapped[str | None] = mapped_column(String(80))
    frequency: Mapped[str | None] = mapped_column(String(100))
    indication: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MedicationState(Base):
    __tablename__ = "medication_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medication_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("medications.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    domain: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    effective_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reason: Mapped[str | None] = mapped_column(Text)
    restart_criteria: Mapped[str | None] = mapped_column(Text)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    physician_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LabResult(Base):
    __tablename__ = "lab_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    test_name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    value_numeric: Mapped[float | None] = mapped_column(Numeric)
    value_text: Mapped[str | None] = mapped_column(String(300))
    units: Mapped[str | None] = mapped_column(String(80))
    reference_range: Mapped[str | None] = mapped_column(String(100))
    abnormal_flag: Mapped[str | None] = mapped_column(String(30))
    collection_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    result_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class VitalSign(Base):
    __tablename__ = "vital_signs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    vital_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    value_numeric: Mapped[float | None] = mapped_column(Numeric)
    value_text: Mapped[str | None] = mapped_column(String(300))
    units: Mapped[str | None] = mapped_column(String(80))
    oxygen_device: Mapped[str | None] = mapped_column(String(100))
    oxygen_flow_lpm: Mapped[float | None] = mapped_column(Numeric)
    observed_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ConsultantRecommendation(Base):
    __tablename__ = "consultant_recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    service: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    consultant_name: Mapped[str | None] = mapped_column(String(200))
    recommendation_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    assessment: Mapped[str | None] = mapped_column(Text)
    recommendation: Mapped[str | None] = mapped_column(Text)
    implementation_status: Mapped[str | None] = mapped_column(String(50))
    current_relevance: Mapped[str | None] = mapped_column(String(50))
    conflict_status: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PendingItem(Base):
    __tablename__ = "pending_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="pending", index=True)
    owner: Mapped[str | None] = mapped_column(String(200))
    clinical_significance: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DispositionState(Base):
    __tablename__ = "disposition_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    anticipated_destination: Mapped[str | None] = mapped_column(String(200))
    current_barriers: Mapped[list | dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    mobility_status: Mapped[str | None] = mapped_column(Text)
    adl_status: Mapped[str | None] = mapped_column(Text)
    pt_recommendation: Mapped[str | None] = mapped_column(Text)
    ot_recommendation: Mapped[str | None] = mapped_column(Text)
    slp_recommendation: Mapped[str | None] = mapped_column(Text)
    oxygen_need: Mapped[str | None] = mapped_column(Text)
    equipment_need: Mapped[str | None] = mapped_column(Text)
    caregiver_support: Mapped[str | None] = mapped_column(Text)
    authorization_status: Mapped[str | None] = mapped_column(Text)
    transportation_status: Mapped[str | None] = mapped_column(Text)
    source_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Contradiction(Base):
    __tablename__ = "contradictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    fact_a_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_facts.id"))
    fact_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_facts.id"))
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, default="moderate", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="unresolved", index=True)
    physician_resolution: Mapped[str | None] = mapped_column(Text)
    resolution_type: Mapped[str | None] = mapped_column(String(50))
    adjudication_reason: Mapped[str | None] = mapped_column(Text)
    source_a_type: Mapped[str | None] = mapped_column(String(60))
    source_a_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_b_type: Mapped[str | None] = mapped_column(String(60))
    source_b_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_fact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_facts.id"))
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ClinicalTrajectory(Base):
    __tablename__ = "clinical_trajectories"
    __table_args__ = (UniqueConstraint("encounter_id", "category", "concept", name="uq_encounter_trajectory_concept"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    concept: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    trend: Mapped[str] = mapped_column(String(40), nullable=False, default="stable")
    earliest_value: Mapped[str | None] = mapped_column(String(200))
    latest_value: Mapped[str | None] = mapped_column(String(200))
    earliest_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    latest_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_ids: Mapped[list | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    interpretation: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

class Procedure(Base):
    __tablename__ = "procedures"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    source_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("source_documents.id"))
    procedure_name: Mapped[str] = mapped_column(String(250), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="planned", index=True)
    planned_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    performed_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    findings: Mapped[str | None] = mapped_column(Text)
    complications: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SafetyFlag(Base):
    __tablename__ = "safety_flags"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    encounter_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("clinical_documents.id"), nullable=False, index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_sections.id"), index=True)
    category: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    claim_text: Mapped[str | None] = mapped_column(Text)
    supporting_evidence: Mapped[list | dict | None] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    resolution: Mapped[str | None] = mapped_column(Text)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    audit_version: Mapped[str] = mapped_column(String(50), nullable=False, default="audit-deterministic-v0.1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
