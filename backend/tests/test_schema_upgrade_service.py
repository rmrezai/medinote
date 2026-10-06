import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from app.db.base import Base
import app.models  # noqa: F401
from app.models import Organization
from app.services.schema_upgrade_service import (
    MRN_UNIQUE_INDEX,
    REQUIRED_LONGITUDINAL_TABLES,
    SCHEMA_UPGRADE_VERSION,
    SchemaUpgradeError,
    apply_schema_upgrades,
)


def test_schema_upgrade_creates_longitudinal_tables_and_mrn_uniqueness():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    assert apply_schema_upgrades(engine) == SCHEMA_UPGRADE_VERSION

    inspector = inspect(engine)
    assert REQUIRED_LONGITUDINAL_TABLES <= set(inspector.get_table_names())

    unique_indexes = {
        row["name"]
        for row in inspector.get_indexes("patients")
        if row.get("unique")
    }
    unique_constraints = {
        row.get("name")
        for row in inspector.get_unique_constraints("patients")
    }
    assert (
        MRN_UNIQUE_INDEX in unique_indexes
        or "uq_patient_organization_mrn" in unique_constraints
    )


def test_schema_upgrade_is_idempotent():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    assert apply_schema_upgrades(engine) == SCHEMA_UPGRADE_VERSION
    assert apply_schema_upgrades(engine) == SCHEMA_UPGRADE_VERSION


def test_duplicate_existing_mrns_fail_closed():
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)

    # Simulate a legacy database: organizations exists and patients predates
    # organization-local MRN uniqueness. No existing rows are rewritten.
    with engine.begin() as connection:
        Organization.__table__.create(connection)
        connection.execute(
            text(
                "CREATE TABLE patients ("
                "id CHAR(32) PRIMARY KEY, "
                "organization_id CHAR(32) NOT NULL, "
                "mrn VARCHAR(100), "
                "first_name VARCHAR(100), "
                "last_name VARCHAR(100), "
                "date_of_birth DATE, "
                "sex VARCHAR(50), "
                "created_at DATETIME)"
            )
        )
        org = uuid.uuid4().hex
        connection.execute(
            text(
                "INSERT INTO patients (id, organization_id, mrn) "
                "VALUES (:id1, :org, :mrn), (:id2, :org, :mrn)"
            ),
            {
                "id1": uuid.uuid4().hex,
                "id2": uuid.uuid4().hex,
                "org": org,
                "mrn": "CLN-DUPLICATE",
            },
        )

    with pytest.raises(
        SchemaUpgradeError,
        match="patient-mrn-duplicates-block-schema-upgrade",
    ):
        apply_schema_upgrades(engine)
