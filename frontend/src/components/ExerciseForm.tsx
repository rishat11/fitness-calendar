import { useState, type FormEvent } from "react";
import { type Exercise, type ExerciseInput } from "../api/client";
import {
  useCreateExercise,
  useUpdateExercise,
} from "../features/exercises/useExercises";
import {
  ALLOWED_WEIGHT_TYPES,
  EQUIPMENT_OPTIONS,
  MUSCLE_OPTIONS,
  WEIGHT_UNIT_OPTIONS,
  defaultWeightStep,
  defaultWeightType,
  weightTypeOptionsFor,
  type Equipment,
  type Muscle,
  type WeightType,
  type WeightUnit,
} from "../features/exercises/options";

const selectClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const labelClass = "flex flex-col gap-1 text-sm font-medium";
const errorClass = "text-sm font-normal text-red-600";

type FormState = {
  name: string;
  primaryMuscle: Muscle | "";
  secondaryMuscles: Muscle[];
  equipment: Equipment;
  weightType: WeightType;
  weightUnit: WeightUnit;
  weightStep: string;
  repMin: string;
  repMax: string;
};

type FieldErrors = Partial<Record<"name" | "primaryMuscle" | "weightStep" | "reps", string>>;

function initialState(exercise: Exercise | undefined, defaultUnit: WeightUnit): FormState {
  if (exercise) {
    return {
      name: exercise.name,
      primaryMuscle: exercise.primary_muscle,
      secondaryMuscles: exercise.secondary_muscles ?? [],
      equipment: exercise.equipment,
      weightType: exercise.weight_type,
      weightUnit: exercise.weight_unit,
      weightStep: exercise.weight_step.toString(),
      repMin: exercise.rep_min.toString(),
      repMax: exercise.rep_max.toString(),
    };
  }
  return {
    name: "",
    primaryMuscle: "",
    secondaryMuscles: [],
    equipment: "barbell",
    weightType: "standard",
    weightUnit: defaultUnit,
    weightStep: defaultWeightStep(defaultUnit).toString(),
    repMin: "8",
    repMax: "12",
  };
}

function parseInteger(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function validate(form: FormState): { errors: FieldErrors; body: ExerciseInput | null } {
  const errors: FieldErrors = {};
  if (form.name.trim() === "") errors.name = "Укажите название";
  if (form.primaryMuscle === "") errors.primaryMuscle = "Выберите основную группу";

  const step = Number(form.weightStep.trim().replace(",", "."));
  if (form.weightStep.trim() === "" || !Number.isFinite(step) || step <= 0 || step > 100) {
    errors.weightStep = "Шаг больше 0 и не больше 100";
  }

  const repMin = parseInteger(form.repMin);
  const repMax = parseInteger(form.repMax);
  if (
    repMin === null ||
    repMax === null ||
    repMin < 1 ||
    repMax > 100 ||
    repMin > repMax
  ) {
    errors.reps = "Повторы от 1 до 100, нижняя граница не больше верхней";
  }

  if (Object.keys(errors).length > 0 || form.primaryMuscle === "" || repMin === null || repMax === null) {
    return { errors, body: null };
  }

  return {
    errors,
    body: {
      name: form.name.trim(),
      primary_muscle: form.primaryMuscle,
      secondary_muscles: form.secondaryMuscles,
      equipment: form.equipment,
      weight_type: form.weightType,
      weight_unit: form.weightUnit,
      weight_step: step,
      rep_min: repMin,
      rep_max: repMax,
    },
  };
}

type ExerciseFormProps = {
  /** Без упражнения форма создаёт новое, с ним — редактирует существующее. */
  exercise?: Exercise;
  defaultWeightUnit?: WeightUnit;
  onDone: () => void;
};

export function ExerciseForm({ exercise, defaultWeightUnit = "kg", onDone }: ExerciseFormProps) {
  const [form, setForm] = useState<FormState>(() => initialState(exercise, defaultWeightUnit));
  const [errors, setErrors] = useState<FieldErrors>({});
  const createExercise = useCreateExercise();
  const updateExercise = useUpdateExercise();
  const mutation = exercise ? updateExercise : createExercise;

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    mutation.reset();
  };

  const toggleSecondary = (muscle: Muscle) => {
    setForm((current) => {
      const has = current.secondaryMuscles.includes(muscle);
      return {
        ...current,
        secondaryMuscles: has
          ? current.secondaryMuscles.filter((item) => item !== muscle)
          : [...current.secondaryMuscles, muscle],
      };
    });
    mutation.reset();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const { errors: nextErrors, body } = validate(form);
    setErrors(nextErrors);
    if (!body) return;

    if (exercise) {
      updateExercise.mutate({ id: exercise.id, body }, { onSuccess: onDone });
    } else {
      createExercise.mutate(body, { onSuccess: onDone });
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label={exercise ? "Редактирование упражнения" : "Новое упражнение"}
      className="flex flex-col gap-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <label className={labelClass}>
        Название
        <input
          className={inputClass}
          value={form.name}
          aria-invalid={errors.name ? true : undefined}
          onChange={(event) => update("name", event.target.value)}
        />
        {errors.name && <span className={errorClass}>{errors.name}</span>}
      </label>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Основная группа
          <select
            className={selectClass}
            value={form.primaryMuscle}
            aria-invalid={errors.primaryMuscle ? true : undefined}
            onChange={(event) => {
              const primary = event.target.value as Muscle | "";
              setForm((current) => ({
                ...current,
                primaryMuscle: primary,
                secondaryMuscles: current.secondaryMuscles.filter((item) => item !== primary),
              }));
              mutation.reset();
            }}
          >
            <option value="">Выберите</option>
            {MUSCLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          {errors.primaryMuscle && <span className={errorClass}>{errors.primaryMuscle}</span>}
        </label>

        <label className={labelClass}>
          Оборудование
          <select
            className={selectClass}
            value={form.equipment}
            onChange={(event) => {
              // Тип учёта веса зависит от оборудования: при смене берём допустимый по умолчанию.
              const equipment = event.target.value as Equipment;
              setForm((current) => ({
                ...current,
                equipment,
                weightType: ALLOWED_WEIGHT_TYPES[equipment].includes(current.weightType)
                  ? current.weightType
                  : defaultWeightType(equipment),
              }));
              mutation.reset();
            }}
          >
            {EQUIPMENT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <fieldset className="flex flex-col gap-2">
        <legend className="text-sm font-medium">Вторичные группы</legend>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {MUSCLE_OPTIONS.filter((option) => option.value !== form.primaryMuscle).map((option) => (
            <label key={option.value} className="flex min-h-11 items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="size-5"
                checked={form.secondaryMuscles.includes(option.value)}
                onChange={() => toggleSecondary(option.value)}
              />
              {option.label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Тип учёта веса
          <select
            className={selectClass}
            value={form.weightType}
            onChange={(event) => update("weightType", event.target.value as WeightType)}
          >
            {weightTypeOptionsFor(form.equipment).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className={labelClass}>
          Единицы веса
          <select
            className={selectClass}
            value={form.weightUnit}
            onChange={(event) => update("weightUnit", event.target.value as WeightUnit)}
          >
            {WEIGHT_UNIT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <label className={labelClass}>
          Шаг повышения
          <input
            className={inputClass}
            inputMode="decimal"
            value={form.weightStep}
            aria-invalid={errors.weightStep ? true : undefined}
            onChange={(event) => update("weightStep", event.target.value)}
          />
          {errors.weightStep && <span className={errorClass}>{errors.weightStep}</span>}
        </label>

        <label className={labelClass}>
          Повторы, от
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.repMin}
            aria-invalid={errors.reps ? true : undefined}
            onChange={(event) => update("repMin", event.target.value)}
          />
        </label>

        <label className={labelClass}>
          Повторы, до
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.repMax}
            aria-invalid={errors.reps ? true : undefined}
            onChange={(event) => update("repMax", event.target.value)}
          />
          {errors.reps && <span className={errorClass}>{errors.reps}</span>}
        </label>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={mutation.isPending}
          className="min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          {mutation.isPending ? "Сохраняем…" : "Сохранить"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="min-h-11 rounded-lg px-5 text-sm font-medium text-slate-600 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800"
        >
          Отмена
        </button>
        {mutation.isError && (
          <span role="alert" className="text-sm text-red-600">
            {mutation.error.message}
          </span>
        )}
      </div>
    </form>
  );
}
