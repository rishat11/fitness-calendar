import { useState, type FormEvent } from "react";
import type { UseQueryResult } from "@tanstack/react-query";
import type { NutritionIntake, NutritionTarget } from "../api/client";
import {
  formatCalories,
  formatGrams,
  macroCalories,
  parseGrams,
} from "../features/nutrition/calories";
import {
  useNutritionIntake,
  useNutritionTarget,
  useUpdateNutritionIntake,
} from "../features/nutrition/useNutrition";

const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const labelClass = "flex flex-col gap-1 text-sm font-medium";
const secondaryClass = "text-slate-600 dark:text-slate-300";

function fieldError(raw: string): string | null {
  if (raw.trim() === "") return null;
  return parseGrams(raw) == null ? "Укажите число от 0 до 2000" : null;
}

function IntakeForm({ intake }: { intake: NutritionIntake }) {
  const [protein, setProtein] = useState(() => formatGrams(intake.protein_g));
  const [fat, setFat] = useState(() => formatGrams(intake.fat_g));
  const [carbs, setCarbs] = useState(() => formatGrams(intake.carbs_g));
  const [saved, setSaved] = useState(false);
  const update = useUpdateNutritionIntake();

  const proteinValue = parseGrams(protein);
  const fatValue = parseGrams(fat);
  const carbsValue = parseGrams(carbs);
  const ready = proteinValue != null && fatValue != null && carbsValue != null;
  // Пока сохранение в пути, калории берутся из полей, а не из ответа сервера.
  const calories = ready
    ? macroCalories({ protein: proteinValue, carbs: carbsValue, fat: fatValue })
    : null;

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!ready) return;
    setSaved(false);
    update.mutate(
      { protein_g: proteinValue, fat_g: fatValue, carbs_g: carbsValue },
      { onSuccess: () => setSaved(true) },
    );
  };

  return (
    <form onSubmit={onSubmit} noValidate className="flex flex-col gap-4">
      <h2 className="text-lg font-semibold">Текущий уровень</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <GramField label="Белки, г" value={protein} onChange={setProtein} />
        <GramField label="Жиры, г" value={fat} onChange={setFat} />
        <GramField label="Углеводы, г" value={carbs} onChange={setCarbs} />
      </div>
      <p className={secondaryClass}>
        Калории:{" "}
        <span className="font-semibold text-slate-900 dark:text-slate-100">
          {calories == null ? "—" : `${formatCalories(calories)} ккал`}
        </span>
      </p>
      <button type="submit" className="btn-primary self-start" disabled={!ready || update.isPending}>
        {update.isPending ? "Сохранение…" : "Сохранить"}
      </button>
      {saved && !update.isPending && (
        <p role="status" className="text-sm text-green-700 dark:text-green-400">
          Сохранено
        </p>
      )}
      {update.isError && (
        <p role="alert" className="text-sm text-red-600">
          {update.error instanceof Error ? update.error.message : "Не удалось сохранить"}
        </p>
      )}
    </form>
  );
}

function GramField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const error = fieldError(value);
  const errorId = `${label}-error`;
  return (
    <label className={labelClass}>
      {label}
      <input
        className={inputClass}
        inputMode="decimal"
        autoComplete="off"
        value={value}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? errorId : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {error && (
        <span id={errorId} className="text-sm font-normal text-red-600">
          {error}
        </span>
      )}
    </label>
  );
}

function TargetBlock({ query }: { query: UseQueryResult<NutritionTarget> }) {
  return (
    <section className="flex flex-col gap-2" aria-labelledby="macro-target-heading">
      <h2 id="macro-target-heading" className="text-lg font-semibold">
        Целевое БЖУ
      </h2>
      {query.isPending && <p className={secondaryClass}>Загрузка…</p>}
      {query.isError && (
        <p className="text-red-600">Не удалось загрузить целевое БЖУ. Обновите страницу.</p>
      )}
      {query.data && !query.data.available && (
        <p className={secondaryClass}>Расчёт появится после замера InBody.</p>
      )}
    </section>
  );
}

export function NutritionPage() {
  const intake = useNutritionIntake();
  const target = useNutritionTarget();

  return (
    <div className="flex max-w-xl flex-col gap-8">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Питание</h1>
        <p className={secondaryClass}>
          Итоги из стороннего трекера. Калории считаются из белков, жиров и углеводов.
        </p>
      </div>
      {intake.isPending && <p className={secondaryClass}>Загрузка…</p>}
      {intake.isError && (
        <p className="text-red-600">Не удалось загрузить питание. Обновите страницу.</p>
      )}
      {intake.data && <IntakeForm intake={intake.data} />}
      <TargetBlock query={target} />
    </div>
  );
}
