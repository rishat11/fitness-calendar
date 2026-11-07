from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Goal = Literal["muscle_gain", "recomposition", "cut", "maintenance"]
Sex = Literal["male", "female"]
WeightUnit = Literal["kg", "lb"]
Theme = Literal["light", "dark", "system"]


class ProfileUpdate(BaseModel):
    """Полная замена профиля: PUT передаёт все поля, пустые опциональные — null.

    Поля без значения по умолчанию обязательны, поэтому частичный ответ не сотрёт данные.
    """

    goal: Goal | None
    height_cm: int | None = Field(ge=100, le=250)
    age: int | None = Field(ge=10, le=120)
    sex: Sex | None
    weight_unit: WeightUnit
    theme: Theme


class ProfileResponse(ProfileUpdate):
    model_config = ConfigDict(from_attributes=True)
