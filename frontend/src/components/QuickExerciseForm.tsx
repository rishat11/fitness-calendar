import { useRef, useState, type FormEvent } from "react";
import { type Exercise } from "../api/client";
import { useCreateExercise } from "../features/exercises/useExercises";
import {
  EQUIPMENT_OPTIONS,
  MUSCLE_OPTIONS,
  buildQuickExerciseInput,
  type Equipment,
  type Muscle,
  type WeightUnit,
} from "../features/exercises/options";

const selectClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const labelClass = "flex flex-col gap-1 text-sm font-medium";

type QuickExerciseFormProps = {
  weightUnit?: WeightUnit;
  /** Вызывается после создания: конструктор тренировки подставляет новое упражнение. */
  onCreated?: (exercise: Exercise) => void;
};

/**
 * Создание упражнения за несколько секунд: название, группа и оборудование.
 * Остальные поля получают значения по умолчанию, их можно поправить позже в полной форме.
 */
export function QuickExerciseForm({ weightUnit = "kg", onCreated }: QuickExerciseFormProps) {
  const [name, setName] = useState("");
  const [primaryMuscle, setPrimaryMuscle] = useState<Muscle | "">("");
  const [equipment, setEquipment] = useState<Equipment>("barbell");
  const [error, setError] = useState<string | null>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const createExercise = useCreateExercise();

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (name.trim() === "") {
      setError("Укажите название");
      return;
    }
    if (primaryMuscle === "") {
      setError("Выберите основную группу");
      return;
    }
    setError(null);
    const body = buildQuickExerciseInput({ name, primaryMuscle, equipment, weightUnit });
    createExercise.mutate(body, {
      onSuccess: (exercise) => {
        setName("");
        nameRef.current?.focus();
        onCreated?.(exercise);
      },
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      aria-label="Быстрое создание упражнения"
      className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <h2 className="text-base font-semibold">Быстрое создание</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <label className={labelClass}>
          Название
          <input
            ref={nameRef}
            className={inputClass}
            value={name}
            aria-invalid={error === "Укажите название" ? true : undefined}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <label className={labelClass}>
          Основная группа
          <select
            className={selectClass}
            value={primaryMuscle}
            onChange={(event) => setPrimaryMuscle(event.target.value as Muscle | "")}
          >
            <option value="">Выберите</option>
            {MUSCLE_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className={labelClass}>
          Оборудование
          <select
            className={selectClass}
            value={equipment}
            onChange={(event) => setEquipment(event.target.value as Equipment)}
          >
            {EQUIPMENT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <button
          type="submit"
          disabled={createExercise.isPending}
          className="min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
        >
          Добавить
        </button>
        {error && (
          <span role="alert" className="text-sm text-red-600">
            {error}
          </span>
        )}
        {createExercise.isError && (
          <span role="alert" className="text-sm text-red-600">
            {createExercise.error.message}
          </span>
        )}
      </div>
    </form>
  );
}
