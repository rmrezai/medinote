from datetime import date, datetime
from uuid import UUID
from pydantic import BaseModel, Field


class PatientCreate(BaseModel):
    mrn: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None


class EncounterCreate(BaseModel):
    organization_id: UUID
    patient: PatientCreate
    admission_datetime: datetime | None = None
    service: str | None = None
    location: str | None = None
    attending_user_id: UUID | None = None


class EncounterRead(BaseModel):
    id: UUID
    patient_id: UUID
    organization_id: UUID
    admission_datetime: datetime | None
    discharge_datetime: datetime | None
    status: str
    service: str | None
    location: str | None
    clinical_state_version: int = 1

    model_config = {"from_attributes": True}


class SourceCreate(BaseModel):
    document_type: str = Field(min_length=1, max_length=50)
    author_name: str | None = None
    author_service: str | None = None
    source_datetime: datetime | None = None
    source_system: str | None = None
    raw_text: str = Field(min_length=1)
    imported_by: UUID | None = None
    asserted_mrn: str | None = None
    asserted_dob: date | None = None
    asserted_name: str | None = None


class SourceRead(BaseModel):
    id: UUID
    encounter_id: UUID
    document_type: str
    source_datetime: datetime | None
    source_system: str | None
    content_hash: str | None
    imported_at: datetime
    identity_status: str = "not_asserted"
    identity_reason: str | None = None

    model_config = {"from_attributes": True}

class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class OrganizationRead(BaseModel):
    id: UUID
    name: str
    active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class EncounterSummary(BaseModel):
    id: UUID
    patient_id: UUID
    organization_id: UUID
    patient_display_name: str | None = None
    mrn: str | None = None
    date_of_birth: date | None = None
    admission_datetime: datetime | None = None
    discharge_datetime: datetime | None = None
    status: str
    service: str | None = None
    location: str | None = None


class FinalTextResponse(BaseModel):
    document_id: UUID
    document_type: str
    status: str
    text: str


class IdentityVerifyRequest(BaseModel):
    confirmed: bool
    reason: str | None = None


class IdentityVerificationRead(BaseModel):
    encounter_id: UUID
    identity_status: str
    verified_by: UUID | None = None
    verified_at: datetime | None = None


class SourceIdentityVerifyRequest(BaseModel):
    confirmed_match: bool
    reason: str | None = None
