from uuid import UUID
from pydantic import BaseModel


class AnalysisReport(BaseModel):
    encounter_id: UUID
    status: str
    extraction_version: str
    sources_analyzed: int
    facts_created: int = 0
    problems_created: int = 0
    medication_states_created: int = 0
    labs_created: int = 0
    vitals_created: int = 0
    consultants_created: int = 0
    pending_items_created: int = 0
    source_reports: list[dict]
    limitations: list[str]
    reconciliation: dict | None = None
    synthesis: dict | None = None
