# services/api/app/schemas_admin.py

from pydantic import BaseModel
from typing import Optional, List, Dict

class AdminSummary(BaseModel):
    total_sessions: int
    total_analyzes_24h: int
    total_donations: int
    total_donations_withdrawn: int
    total_labeled: int
    consent_opt_in_progress_pct: float
    consent_opt_in_donate_pct: float
    active_model_version: Optional[str] = None

class AdminAuditEvent(BaseModel):
    id: int
    created_at: str
    event_type: str
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    client_ip: Optional[str] = None
    payload_json: Optional[str] = None

class AdminAuditPage(BaseModel):
    items: List[AdminAuditEvent]
    next_before_id: Optional[int] = None
