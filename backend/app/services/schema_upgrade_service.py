"""Idempotent schema upgrades for longitudinal MediNote clinical data.

MediNote historically used Base.metadata.create_all() during startup. That creates
new tables but does not retrofit constraints onto pre-existing tables. This
module preserves create_all behavior and adds explicit verification plus the
organization-local patient MRN uniqueness retrofit required by the longitudinal
record foundation.

Schema preparation does not enable PHI, clinical writes, external integrations,
or production activation.
"""
from __future__ import annotations

from sqlalchemy import Index, inspect, select, func
from sqlalchemy.engine import Engine

from app.db.base import Base
from app.models import Patient


SCHEMA_UPGRADE_VERSION = "medinote-schema-upgrade-v1"

REQUIRED_LONGITUDINAL_TABLES = frozenset(
    {
        "patient_external_identifiers",
        "patient_problem_list_entries",
        "encounter_diagnosis_classifications",
        "patient_medication_profile_entries",
        "patient_allergy_intolerance_entries",
        "external_medication_allergy_observations",
        "medication_allergy_reconciliation_episodes",
    }
)

MRN_UNIQUE_INDEX = "ux_patients_organization_mrn"


class SchemaUpgradeError(RuntimeError):
    """Raised when an existing database cannot be upgraded safely."""


def _has_org_mrn_uniqueness(connection) -> bool:
    inspector = inspect(connection)

    try:
        constraints = inspector.get_unique_constraints("patients")
    except NotImplementedError:
        constraints = []
    for item in constraints:
        columns = tuple(item.get("column_names") or ())
        if set(columns) == {"organization_id", "mrn"}:
            return True

    for item in inspector.get_indexes("patients"):
        columns = tuple(item.get("column_names") or ())
        if item.get("unique") and set(columns) == {"organization_id", "mrn"}:
            return True

    return False


def _find_duplicate_mrns(connection):
    stmt = (
        select(
            Patient.organization_id,
            Patient.mrn,
            func.count(Patient.id).label("row_count"),
        )
        .where(Patient.mrn.is_not(None))
        .group_by(Patient.organization_id, Patient.mrn)
        .having(func.count(Patient.id) > 1)
        .limit(10)
    )
    return list(connection.execute(stmt).all())


def _ensure_org_mrn_uniqueness(connection) -> None:
    if _has_org_mrn_uniqueness(connection):
        return

    duplicates = _find_duplicate_mrns(connection)
    if duplicates:
        raise SchemaUpgradeError(
            "patient-mrn-duplicates-block-schema-upgrade"
        )

    Index(
        MRN_UNIQUE_INDEX,
        Patient.__table__.c.organization_id,
        Patient.__table__.c.mrn,
        unique=True,
    ).create(bind=connection)


def verify_longitudinal_schema(connection) -> None:
    inspector = inspect(connection)
    tables = set(inspector.get_table_names())
    missing = sorted(REQUIRED_LONGITUDINAL_TABLES - tables)
    if missing:
        raise SchemaUpgradeError(
            "missing-longitudinal-tables:" + ",".join(missing)
        )
    if "patients" not in tables:
        raise SchemaUpgradeError("patients-table-missing")
    if not _has_org_mrn_uniqueness(connection):
        raise SchemaUpgradeError("patient-mrn-uniqueness-missing")


def apply_schema_upgrades(engine: Engine) -> str:
    """Create missing tables, retrofit safe constraints, and verify the result.

    The operation is intentionally idempotent. Existing rows are never rewritten.
    If duplicate non-null MRNs would make the uniqueness constraint unsafe, the
    upgrade fails closed and requires explicit reconciliation.
    """
    Base.metadata.create_all(bind=engine)

    with engine.begin() as connection:
        _ensure_org_mrn_uniqueness(connection)
        verify_longitudinal_schema(connection)

    return SCHEMA_UPGRADE_VERSION


__all__ = [
    "SCHEMA_UPGRADE_VERSION",
    "REQUIRED_LONGITUDINAL_TABLES",
    "MRN_UNIQUE_INDEX",
    "SchemaUpgradeError",
    "apply_schema_upgrades",
    "verify_longitudinal_schema",
]
