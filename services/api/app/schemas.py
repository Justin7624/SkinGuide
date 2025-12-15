# services/api/app/schemas.py

from pydantic import BaseModel, Field
from typing import List, Literal, Optional, Dict

AttributeKey = Literal[
    "uneven_tone_appearance",
    "hyperpigmentation_appearance",
    "redness_appearance",
    "texture_roughness_appearance",
    "shine_oiliness_appearance",
    "pore_visibility_appearance",
    "fine_lines_appearance",
    "dryness_flaking_appearance",
]

RegionName = Literal["forehead", "left_cheek", "right_cheek", "nose", "chin"]

class AttributeScore(BaseModel):
    key: AttributeKey
    score: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)

class QualityReport(BaseModel):
    lighting: Literal["ok", "low", "harsh"]
    blur: Literal["low", "medium", "high"]
    angle: Literal["ok", "bad"]
    makeup_suspected: bool = False

class BBox(BaseModel):
    x: int
    y: int
    w: int
    h: int

class RegionResult(BaseModel):
    name: RegionName
    bbox: BBox
    skin_pixels: int = Field(ge=0)
    quality: QualityReport
    attributes: List[AttributeScore] = Field(default_factory=list)
    status: Literal["ok", "insufficient_skin"] = "ok"

class AnalyzeResponse(BaseModel):
    disclaimer: str
    quality: QualityReport
    attributes: List[AttributeScore]
    regions: List[RegionResult] = Field(default_factory=list)
    routine: dict
    professional_to_discuss: List[str]
    when_to_seek_care: List[str]
    model_version: str
    stored_for_progress: bool = False

    # NEW: used to attach labels/donations to the same ROI sample
    roi_sha256: Optional[str] = None

class ConsentUpsert(BaseModel):
    store_progress_images: bool
    donate_for_improvement: bool

class SessionCreateResponse(BaseModel):
    session_id: str
    store_images_default: bool

class DonateResponse(BaseModel):
    ok: bool
    stored: bool
    reason: Optional[str] = None
    roi_sha256: Optional[str] = None

class LabelUpsert(BaseModel):
    """
    Sparse labels allowed: provide only what the user wants to label.
    Values are normalized 0..1 (e.g. mild=0.33, moderate=0.66, severe=1.0).
    """
    roi_sha256: str
    labels: Dict[AttributeKey, float] = Field(default_factory=dict)
    # Optional metadata (helps fairness analysis if voluntarily provided)
    fitzpatrick: Optional[Literal["I","II","III","IV","V","VI"]] = None
    age_band: Optional[Literal["<18","18-24","25-34","35-44","45-54","55-64","65+"]] = None

class LabelResponse(BaseModel):
    ok: bool
    stored: bool
    reason: Optional[str] = None
    roi_sha256: Optional[str] = None
