import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


J = JSON().with_variant(JSONB(), "postgresql")


class PatientMedicationProfileEntry(Base):
    """Patient-scoped longitudinal medication list entry.

    External EHR/pharmacy history does not directly make an item current.
    Current status requires explicit reconciliation/clinician confirmation.
    """

    __tablename__ = "patient_medication_profile_entries"
    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "normalized_name",
            "status",
            name="uq_patient_medication_name_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    normalized_name: Mapped[str] = mapped_column(String(220), nullable=False, index=True)
    display_name: Mapped[str | None] = mapped_column(String(300))
    rxnorm_cui: Mapped[str | None] = mapped_column(String(40), index=True)
    dose: Mapped[str | None] = mapped_column(String(120))
    route: Mapped[str | None] = mapped_column(String(80))
    frequency: Mapped[str | None] = mapped_column(String(120))
    indication: Mapped[str | None] = mapped_column(String(300))
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="current", index=True
    )  # current | prior | unknown | entered-in-error
    source_encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), index=True
    )
    clinician_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_reconciled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PatientAllergyIntoleranceEntry(Base):
    """Patient-scoped allergy/intolerance/adverse-reaction record."""

    __tablename__ = "patient_allergy_intolerance_entries"
    __table_args__ = (
        UniqueConstraint(
            "patient_id",
            "substance_code_system",
            "substance_code",
            "clinical_status",
            name="uq_patient_allergy_substance_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    substance_display: Mapped[str] = mapped_column(String(300), nullable=False)
    substance_code_system: Mapped[str] = mapped_column(
        String(80), nullable=False, default="text"
    )
    substance_code: Mapped[str] = mapped_column(String(120), nullable=False)
    rxnorm_cui: Mapped[str | None] = mapped_column(String(40), index=True)
    allergy_type: Mapped[str] = mapped_column(
        String(40), nullable=False, default="allergy", index=True
    )  # allergy | intolerance | adverse-reaction
    clinical_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )  # active | inactive | resolved | entered-in-error
    verification_status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="unconfirmed", index=True
    )  # unconfirmed | confirmed | refuted
    reaction_text: Mapped[str | None] = mapped_column(Text)
    reaction_severity: Mapped[str | None] = mapped_column(String(30))
    onset_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), index=True
    )
    clinician_confirmed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExternalMedicationAllergyObservation(Base):
    """Normalized provenance record from EHR/pharmacy/med-history adapters.

    This table captures source evidence. It does not directly change the
    authoritative patient medication or allergy list.
    """

    __tablename__ = "external_medication_allergy_observations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_system",
            "external_record_ref",
            name="uq_external_medallergy_source_ref",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    source_system: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_record_ref: Mapped[str] = mapped_column(String(200), nullable=False)
    item_kind: Mapped[str] = mapped_column(
        String(40), nullable=False, index=True
    )  # medication | allergy
    code_system: Mapped[str | None] = mapped_column(String(80))
    code: Mapped[str | None] = mapped_column(String(120))
    rxnorm_cui: Mapped[str | None] = mapped_column(String(40), index=True)
    display_text: Mapped[str] = mapped_column(String(300), nullable=False)
    source_status: Mapped[str | None] = mapped_column(String(80))
    effective_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    source_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    payload_sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    provenance_json: Mapped[dict] = mapped_column(J, nullable=False, default=dict)
    reconciliation_status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="unreviewed", index=True
    )  # unreviewed | accepted | rejected | duplicate
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MedicationAllergyReconciliationEpisode(Base):
    """Encounter-linked clinician reconciliation state."""

    __tablename__ = "medication_allergy_reconciliation_episodes"
    __table_args__ = (
        UniqueConstraint(
            "encounter_id",
            name="uq_medallergy_reconciliation_encounter",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("patients.id"), nullable=False, index=True
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("encounters.id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(40), nullable=False, default="pending", index=True
    )  # pending | in-review | complete
    source_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    discrepancy_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    clinician_review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
