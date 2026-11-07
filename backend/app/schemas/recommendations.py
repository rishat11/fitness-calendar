from typing import Literal

from pydantic import BaseModel, ConfigDict

RecommendationCode = Literal[
    "low_protein",
    "low_fat",
    "insufficient_scans",
    "trend_keep",
    "trend_surplus",
    "trend_reduce",
    "trend_ease_deficit",
    "guard_low_calories",
    "guard_fast_loss",
    "guard_low_body_fat",
    "no_intake",
]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BasisItem(_Strict):
    label: str
    value: str


class RecommendationItem(_Strict):
    code: RecommendationCode
    text: str
    basis: list[BasisItem]


class RecommendationsResponse(_Strict):
    items: list[RecommendationItem]
    disclaimer: str
