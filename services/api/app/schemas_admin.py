# services/api/app/schemas_admin.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal

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

# ---- UI-ready metrics ----

class TimePoint(BaseModel):
    date: str  # YYYY-MM-DD
    value: int

class MultiSeries(BaseModel):
    start_date: str
    end_date: str
    series: Dict[str, List[TimePoint]]

class BreakdownItem(BaseModel):
    key: str
    value: int

class Breakdown(BaseModel):
    items: List[BreakdownItem] = Field(default_factory=list)

class AdminMetricsResponse(BaseModel):
    start_date: str
    end_date: str

    analyzes: List[TimePoint] = Field(default_factory=list)
    sessions: List[TimePoint] = Field(default_factory=list)

    donations_created: List[TimePoint] = Field(default_factory=list)
    donations_withdrawn: List[TimePoint] = Field(default_factory=list)
    labels_created: List[TimePoint] = Field(default_factory=list)

    event_type_breakdown_24h: Breakdown = Field(default_factory=Breakdown)
    model_version_breakdown_24h: Breakdown = Field(default_factory=Breakdown)

class ModelRow(BaseModel):
    version: str
    created_at: str
    is_active: bool
    model_uri: str
    manifest_uri: str
    metrics_json: Optional[str] = None

class ModelTable(BaseModel):
    active_version: Optional[str] = None
    items: List[ModelRow] = Field(default_factory=list)
