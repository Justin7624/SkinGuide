# services/api/app/schemas_legal.py

from pydantic import BaseModel, Field
from typing import Literal, Optional

DocKey = Literal["privacy_policy", "terms_of_use", "consent_copy"]

class LegalDoc(BaseModel):
    key: DocKey
    version: str
    effective_at: str
    body_markdown: str

class LegalDocSummary(BaseModel):
    key: DocKey
    version: str
    effective_at: str

class LegalBundle(BaseModel):
    privacy_policy: LegalDoc
    terms_of_use: LegalDoc
    consent_copy: LegalDoc

class UpsertLegalDocRequest(BaseModel):
    key: DocKey
    version: str
    effective_at: Optional[str] = None  # ISO8601; if omitted, now
    body_markdown: str = Field(min_length=10)

class UpsertLegalDocResponse(BaseModel):
    ok: bool
    reason: Optional[str] = None
