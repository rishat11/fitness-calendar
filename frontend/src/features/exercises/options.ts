import type { Exercise, ExerciseInput } from "../../api/client";

export type Muscle = ExerciseInput["primary_muscle"];
export type Equipment = ExerciseInput["equipment"];
export type WeightType = ExerciseInput["weight_type"];
export type WeightUnit = ExerciseInput["weight_unit"];

type Option<T extends string> = { value: T; label: string };

export const MUSCLE_OPTIONS: Option<Muscle>[] = [
  { value: "chest", label: "Грудь" },
  { value: "back", label: "Спина" },
  { value: "shoulders", label: "Плечи" },
  { value: "biceps", label: "Бицепс" },
  { value: "triceps", label: "Трицепс" },
  { value: "forearms", label: "Предплечья" },
  { value: "quadriceps", label: "Квадрицепсы" },
  { value: "hamstrings", label: "Бицепс бедра" },
  { value: "glutes", label: "Ягодицы" },
  { value: "calves", label: "Икры" },
  { value: "core", label: "Кор (пресс)" },
];

export const EQUIPMENT_OPTIONS: Option<Equipment>[] = [
  { value: "barbell", label: "Штанга" },
  { value: "dumbbell", label: "Гантели" },
  { value: "machine", label: "Тренажёр" },
  { value: "cable", label: "Блок" },
  { value: "bodyweight", label: "Собственный вес" },
];

export const WEIGHT_TYPE_OPTIONS: Option<WeightType>[] = [
  { value: "standard", label: "Обычный вес" },
  { value: "per_dumbbell", label: "Вес на каждую гантель" },
  { value: "stack", label: "Стопка тренажёра" },
  { value: "stack_plus_extra", label: "Стопка + доп. вес" },
  { value: "bodyweight_plus", label: "Вес тела + отягощение" },
  { value: "bodyweight_assisted", label: "Вес тела − помощь (гравитрон)" },
];

/** Зеркалит правило бэкенда (app/schemas/exercise.py): какой учёт веса допустим для оборудования. */
export const ALLOWED_WEIGHT_TYPES: Record<Equipment, WeightType[]> = {
  barbell: ["standard"],
  dumbbell: ["standard", "per_dumbbell"],
  machine: ["standard", "stack", "stack_plus_extra", "bodyweight_assisted"],
  cable: ["stack", "stack_plus_extra"],
  bodyweight: ["bodyweight_plus", "bodyweight_assisted"],
};

export function weightTypeOptionsFor(equipment: Equipment): Option<WeightType>[] {
  const allowed = ALLOWED_WEIGHT_TYPES[equipment];
  return WEIGHT_TYPE_OPTIONS.filter((option) => allowed.includes(option.value));
}

/** Тип по умолчанию для оборудования: самый частый для него. */
const DEFAULT_WEIGHT_TYPE: Record<Equipment, WeightType> = {
  barbell: "standard",
  dumbbell: "standard",
  machine: "stack",
  cable: "stack",
  bodyweight: "bodyweight_plus",
};

export function defaultWeightType(equipment: Equipment): WeightType {
  return DEFAULT_WEIGHT_TYPE[equipment];
}

export const WEIGHT_UNIT_OPTIONS: Option<WeightUnit>[] = [
  { value: "kg", label: "Килограммы (кг)" },
  { value: "lb", label: "Фунты (lb)" },
];

export function labelFor<T extends string>(options: Option<T>[], value: T): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

/** Шаг по умолчанию: 2,5 кг или 5 lb — типичный шаг блинов. */
export function defaultWeightStep(unit: WeightUnit): number {
  return unit === "kg" ? 2.5 : 5;
}

/** Быстрое создание задаёт только название, группу и оборудование; остальное — разумные значения по умолчанию. */
export function buildQuickExerciseInput(params: {
  name: string;
  primaryMuscle: Muscle;
  equipment: Equipment;
  weightUnit: WeightUnit;
}): ExerciseInput {
  return {
    name: params.name.trim(),
    primary_muscle: params.primaryMuscle,
    secondary_muscles: [],
    equipment: params.equipment,
    weight_type: defaultWeightType(params.equipment),
    weight_unit: params.weightUnit,
    weight_step: defaultWeightStep(params.weightUnit),
    rep_min: 8,
    rep_max: 12,
  };
}

export function describeExercise(exercise: Exercise): string {
  return [
    labelFor(MUSCLE_OPTIONS, exercise.primary_muscle),
    labelFor(EQUIPMENT_OPTIONS, exercise.equipment),
  ].join(" · ");
}
