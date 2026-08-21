from uuid import UUID

from sqlalchemy.orm import Session

from app.models import Encounter


def bump_state_version(db: Session, encounter_id: UUID) -> int:
    encounter = db.get(Encounter, encounter_id)
    if encounter is None:
        raise LookupError("Encounter not found")
    encounter.clinical_state_version = int(encounter.clinical_state_version or 1) + 1
    return encounter.clinical_state_version


def document_state_status(db: Session, document) -> dict:
    encounter = db.get(Encounter, document.encounter_id)
    current = int(encounter.clinical_state_version or 1) if encounter else int(document.generated_state_version or 1)
    generated = int(document.generated_state_version or 1)
    return {"generated_state_version": generated, "current_state_version": current, "stale": generated != current}
