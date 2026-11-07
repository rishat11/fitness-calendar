import { useEffect, useRef, useState } from "react";
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

/** Ждём паузу в наборе, чтобы не отправлять незаконченное число вроде «1» при вводе «100». */
const TEXT_SAVE_DELAY_MS = 400;

type GramsForm = {
  protein: string;
  fat: string;
  carbs: string;
};

function fieldError(raw: string): string | null {
  if (raw.trim() === "") return null;
  return parseGrams(raw) == null ? "Укажите число от 0 до 2000" : null;
}

function IntakeForm({ intake }: { intake: NutritionIntake }) {
  const [form, setForm] = useState<GramsForm>(() => ({
    protein: formatGrams(intake.protein_g),
    fat: formatGrams(intake.fat_g),
    carbs: formatGrams(intake.carbs_g),
  }));
  const [saved, setSaved] = useState(false);
  const update = useUpdateNutritionIntake();
  const formRef = useRef(form);
  const saveTimer = useRef<number | null>(null);
  const saveGeneration = useRef(0);

  useEffect(() => {
    return () => {
      if (saveTimer.current !== null) {
        window.clearTimeout(saveTimer.current);
      }
    };
  }, []);

  const proteinValue = parseGrams(form.protein);
  const fatValue = parseGrams(form.fat);
  const carbsValue = parseGrams(form.carbs);
  const ready = proteinValue != null && fatValue != null && carbsValue != null;
  // Пока сохранение в пути, калории берутся из полей, а не из ответа сервера.
  const calories = ready
    ? macroCalories({ protein: proteinValue, carbs: carbsValue, fat: fatValue })
    : null;

  const persist = (next: GramsForm) => {
    const generation = ++saveGeneration.current;
    const protein = parseGrams(next.protein);
    const fat = parseGrams(next.fat);
    const carbs = parseGrams(next.carbs);
    if (protein == null || fat == null || carbs == null) {
      setSaved(false);
      return;
    }
    const current = intake;
    if (protein === current.protein_g && fat === current.fat_g && carbs === current.carbs_g) {
      setSaved(true);
      return;
    }
    update.mutate(
      { protein_g: protein, fat_g: fat, carbs_g: carbs },
      {
        onSuccess: () => {
          if (generation === saveGeneration.current) {
            setSaved(true);
          }
        },
      },
    );
  };

  const clearSaveTimer = () => {
    if (saveTimer.current !== null) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
  };

  const updateField = (key: keyof GramsForm, value: string) => {
    const next = { ...formRef.current, [key]: value };
    formRef.current = next;
    setForm(next);
    setSaved(false);
    update.reset();
    clearSaveTimer();
    saveTimer.current = window.setTimeout(() => {
      saveTimer.current = null;
      persist(next);
    }, TEXT_SAVE_DELAY_MS);
  };

  const flushTextSave = () => {
    if (saveTimer.current === null) {
      return;
    }
    clearSaveTimer();
    persist(formRef.current);
  };

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        flushTextSave();
      }}
      noValidate
      className="flex flex-col gap-4"
    >
      <h2 className="text-lg font-semibold">Текущий уровень</h2>
      <div className="grid gap-4 sm:grid-cols-3">
        <GramField
          label="Белки, г"
          value={form.protein}
          onChange={(value) => updateField("protein", value)}
          onBlur={flushTextSave}
        />
        <GramField
          label="Жиры, г"
          value={form.fat}
          onChange={(value) => updateField("fat", value)}
          onBlur={flushTextSave}
        />
        <GramField
          label="Углеводы, г"
          value={form.carbs}
          onChange={(value) => updateField("carbs", value)}
          onBlur={flushTextSave}
        />
      </div>
      <p className={secondaryClass}>
        Калории:{" "}
        <span className="font-semibold text-slate-900 dark:text-slate-100">
          {calories == null ? "—" : `${formatCalories(calories)} ккал`}
        </span>
      </p>
      <div className="flex flex-wrap items-center gap-3">
        {update.isPending && (
          <span role="status" className="text-sm text-slate-600 dark:text-slate-300">
            Сохраняем…
          </span>
        )}
        {saved && !update.isPending && (
          <span role="status" className="text-sm text-green-700 dark:text-green-400">
            Сохранено
          </span>
        )}
        {update.isError && (
          <span role="alert" className="text-sm text-red-600">
            {update.error instanceof Error ? update.error.message : "Не удалось сохранить"}
          </span>
        )}
      </div>
    </form>
  );
}

function GramField({
  label,
  value,
  onChange,
  onBlur,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
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
        onBlur={onBlur}
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
      {query.data && !query.data.available && query.data.reason === "нет замера InBody" && (
        <p className={secondaryClass}>Расчёт появится после замера InBody.</p>
      )}
      {query.data && !query.data.available && query.data.reason !== "нет замера InBody" && (
        <p className={secondaryClass}>{query.data.reason}</p>
      )}
      {query.data?.available && (
        <ul className="flex flex-col gap-1 text-sm">
          <li>Белки: {query.data.protein_g} г</li>
          <li>Жиры: {query.data.fat_g} г</li>
          <li>Углеводы: {query.data.carbs_g} г</li>
          <li>Калории: {query.data.calories} ккал</li>
        </ul>
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
