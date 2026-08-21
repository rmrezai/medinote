from uuid import UUID
from pydantic import BaseModel


class SynthesisReport(BaseModel):
    encounter_id: UUID
    status: str
    synthesis_version: str
    problems_processed: int
    problem_fields_updated: int
    evidence_links_created: int
    problems: list[dict]
    rules: list[str]
