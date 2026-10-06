import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatientExternalIdentifier(Base):
    """External-system patient identifier mapped to one internal patient record.

    External identifiers are PHI and belong inside the approved clinical data
    boundary. They never replace the internal Clinistry/MediNote MRN.
    """

    __tablename__ = "patient_external_identifiers"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "source_system",
            "identifier_type",
            "identifier_value",
            name="uq_external_patient_identifier",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id"),
        nullable=False,
        index=True,
    )
    source_system: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    identifier_type: Mapped[str] = mapped_column(
        String(60), nullable=False, default="external-mrn", index=True
    )
    identifier_value: Mapped[str] = mapped_column(String(200), nullable=False)
    assigning_authority: Mapped[str | None] = mapped_column(String(200))
    source_record_ref: Mapped[str | None] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
