from __future__ import annotations

from pydantic import BaseModel, Field


class AffectToneSnapshot(BaseModel):
    civility_score: float = 0.0
    harsh_msg_ratio: float = 0.0
    polite_msg_ratio: float = 0.0
    punct_aggression_avg: float = 0.0


class AffectRefineProfileSample(BaseModel):
    message_count: int = 0
    answer_count: int = 0
    window_hours: int = 168


class AffectRefineProfileRaw(BaseModel):
    repeat_chain_rate: float = 0.0
    local_answer_ratio: float = 0.0
    affect_tone: AffectToneSnapshot | None = None


class AffectRefineProfileDerived(BaseModel):
    warmth_bias: float = 0.0
    assertiveness_bias: float = 0.0
    length_pref: str = "medium"
    chaos_bias: float = 0.0


class AffectRefineProfile(BaseModel):
    sample: AffectRefineProfileSample | None = None
    raw: AffectRefineProfileRaw | None = None
    derived: AffectRefineProfileDerived | None = None


class AffectRefineRequest(BaseModel):
    group_id: int = Field(ge=0)
    profile: AffectRefineProfile
    hints: list[str] = Field(default_factory=list)
    message_samples: list[str] = Field(default_factory=list, max_length=12)


class AffectTriggerSuggestion(BaseModel):
    phrase: str = Field(min_length=1, max_length=64)
    warmth_delta: float = 0.0
    assertiveness_delta: float = 0.0
    ttl_hours: int = Field(default=168, ge=1, le=720)


class AffectRefineResponse(BaseModel):
    warmth_delta: float = 0.0
    assertiveness_delta: float = 0.0
    confidence: float = 0.0
    summary: str = ""
    triggers: list[AffectTriggerSuggestion] = Field(default_factory=list)


class AffectRefineError(BaseModel):
    error: str
