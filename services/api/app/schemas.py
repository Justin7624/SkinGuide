from pydantic import BaseModel, Field
from typing import List, Literal, Optional

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
