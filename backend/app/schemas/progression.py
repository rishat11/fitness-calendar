import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.profile import WeightUnit

HintStatus = Literal["increase_weight", "continue", "stagnation"]
DecisionAction = Literal["accept", "reject"]


class ProgressionHintResponse(BaseModel):
    """Подсказка двойной прогрессии. Сама по себе шаблон и план не меняет."""

    exercise_id: uuid.UUID
    status: HintStatus
    message: str
    suggested_weight: float | None
    weight_unit: WeightUnit | None
    last_session_id: uuid.UUID
    # Расчётный 1ПМ лучшего рабочего подхода последней сессии. Не цель и не график.
    epley_1rm: float | None


class ProgressionDecisionWrite(BaseModel):
    action: DecisionAction
    # Какой открытый лог заполнять. Без id берётся последний незавершённый с этим упражнением.
    performed_id: uuid.UUID | None = None


class ProgressionDecisionResult(BaseModel):
    action: DecisionAction
    performed_id: uuid.UUID | None = None
    set_id: uuid.UUID | None = None
    weight: float | None = Field(default=None, ge=0, le=2000)
