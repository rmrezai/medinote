from uuid import UUID
from pydantic import BaseModel

from app.schemas.progress import ProgressDocumentResponse


class SignoutGenerateRequest(BaseModel):
    variant: str = "standard"
    generated_by: UUID | None = None


SignoutDocumentResponse = ProgressDocumentResponse
