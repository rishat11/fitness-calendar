import uuid
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from app.schemas.profile import WeightUnit

Muscle = Literal[
    "chest",
    "back",
    "shoulders",
    "biceps",
    "triceps",
    "forearms",
    "quadriceps",
    "hamstrings",
    "glutes",
    "calves",
    "core",
]
Equipment = Literal["barbell", "dumbbell", "machine", "cable", "bodyweight"]
# standard — обычный вес; per_dumbbell — вес на каждую гантель;
# stack — только стопка тренажёра; stack_plus_extra — стопка плюс доп. вес;
# bodyweight_plus — вес тела плюс отягощение; bodyweight_assisted — вес тела минус помощь.
WeightType = Literal[
    "standard",
    "per_dumbbell",
    "stack",
    "stack_plus_extra",
    "bodyweight_plus",
    "bodyweight_assisted",
]

# Какой учёт веса имеет смысл для оборудования. Например, у штанги нет «веса тела плюс отягощение».
# Гравитрон — тренажёр с помощью, поэтому у тренажёра допустим «вес тела минус помощь».
ALLOWED_WEIGHT_TYPES: dict[str, frozenset[str]] = {
    "barbell": frozenset({"standard"}),
    "dumbbell": frozenset({"standard", "per_dumbbell"}),
    "machine": frozenset({"standard", "stack", "stack_plus_extra", "bodyweight_assisted"}),
    "cable": frozenset({"stack", "stack_plus_extra"}),
    "bodyweight": frozenset({"bodyweight_plus", "bodyweight_assisted"}),
}

ExerciseName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)
]


class ExerciseInput(BaseModel):
    """Полная замена упражнения: PUT передаёт все поля, как и для профиля."""

    name: ExerciseName
    primary_muscle: Muscle
    secondary_muscles: list[Muscle] = Field(default_factory=list, max_length=5)
    equipment: Equipment
    weight_type: WeightType
    weight_unit: WeightUnit
    weight_step: float = Field(gt=0, le=100)
    rep_min: int = Field(ge=1, le=100)
    rep_max: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def check_muscles_and_reps(self) -> Self:
        if len(set(self.secondary_muscles)) != len(self.secondary_muscles):
            raise ValueError("вторичные группы не должны повторяться")
        if self.primary_muscle in self.secondary_muscles:
            raise ValueError("основная группа не может быть одновременно вторичной")
        if self.weight_type not in ALLOWED_WEIGHT_TYPES[self.equipment]:
            raise ValueError("этот тип учёта веса не подходит для выбранного оборудования")
        if self.rep_min > self.rep_max:
            raise ValueError("нижняя граница повторов больше верхней")
        return self


class ExerciseResponse(ExerciseInput):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    archived: bool
