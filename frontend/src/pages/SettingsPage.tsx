import { useEffect, useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, type ExportDocument, type Profile, type ProfileUpdate } from "../api/client";
import { ME_QUERY_KEY } from "../features/auth/useAuth";
import { backupFilename, saveBlob } from "../features/transfer/download";
import { toProfileUpdate, useProfile, useUpdateProfile } from "../features/profile/useProfile";

const GOAL_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Не выбрана" },
  { value: "muscle_gain", label: "Набор мышц" },
  { value: "recomposition", label: "Рекомпозиция" },
  { value: "cut", label: "Сушка" },
  { value: "maintenance", label: "Поддержание" },
];

const SEX_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "Не указан" },
  { value: "male", label: "Мужской" },
  { value: "female", label: "Женский" },
];

const UNIT_OPTIONS: { value: ProfileUpdate["weight_unit"]; label: string }[] = [
  { value: "kg", label: "Килограммы (кг)" },
  { value: "lb", label: "Фунты (lb)" },
];

const THEME_OPTIONS: { value: ProfileUpdate["theme"]; label: string }[] = [
  { value: "system", label: "Как в системе" },
  { value: "light", label: "Светлая" },
  { value: "dark", label: "Тёмная" },
];

const selectClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const labelClass = "flex flex-col gap-1 text-sm font-medium";

/** Ждём паузу в наборе, чтобы не отправлять незаконченное число вроде «18» при вводе «180». */
const TEXT_SAVE_DELAY_MS = 400;

type FormState = {
  goal: string;
  height: string;
  age: string;
  sex: string;
  weightUnit: ProfileUpdate["weight_unit"];
  theme: ProfileUpdate["theme"];
};

type ParseResult = { ok: true; value: number | null } | { ok: false };

/** Пустое поле означает «не указано»; иначе число в диапазоне, который проверяет и сервер. */
function parseBounded(raw: string, min: number, max: number): ParseResult {
  const trimmed = raw.trim();
  if (trimmed === "") {
    return { ok: true, value: null };
  }
  const value = Number(trimmed);
  if (!Number.isInteger(value) || value < min || value > max) {
    return { ok: false };
  }
  return { ok: true, value };
}

function toForm(profile: Profile): FormState {
  return {
    goal: profile.goal ?? "",
    height: profile.height_cm?.toString() ?? "",
    age: profile.age?.toString() ?? "",
    sex: profile.sex ?? "",
    weightUnit: profile.weight_unit,
    theme: profile.theme,
  };
}

function ProfileForm({ profile }: { profile: Profile }) {
  const [form, setForm] = useState<FormState>(() => toForm(profile));
  const [errors, setErrors] = useState<Partial<Record<"height" | "age", string>>>({});
  const [saved, setSaved] = useState(false);
  const updateProfile = useUpdateProfile();
  const formRef = useRef(form);
  const saveTimer = useRef<number | null>(null);
  const saveGeneration = useRef(0);
  formRef.current = form;

  useEffect(() => {
    return () => {
      if (saveTimer.current !== null) {
        window.clearTimeout(saveTimer.current);
      }
    };
  }, []);

  const persist = (next: FormState) => {
    const generation = ++saveGeneration.current;
    const height = parseBounded(next.height, 100, 250);
    const age = parseBounded(next.age, 10, 120);
    const nextErrors: typeof errors = {};
    if (!height.ok) nextErrors.height = "Укажите рост от 100 до 250 см";
    if (!age.ok) nextErrors.age = "Укажите возраст от 10 до 120 лет";
    setErrors(nextErrors);
    if (!height.ok || !age.ok) {
      setSaved(false);
      return;
    }

    const body = toProfileUpdate(profile, {
      goal: next.goal === "" ? null : (next.goal as ProfileUpdate["goal"]),
      height_cm: height.value,
      age: age.value,
      sex: next.sex === "" ? null : (next.sex as ProfileUpdate["sex"]),
      weight_unit: next.weightUnit,
      theme: next.theme,
    });
    if (
      body.goal === profile.goal &&
      body.height_cm === profile.height_cm &&
      body.age === profile.age &&
      body.sex === profile.sex &&
      body.weight_unit === profile.weight_unit &&
      body.theme === profile.theme
    ) {
      setSaved(true);
      return;
    }
    updateProfile.mutate(body, {
      onSuccess: () => {
        if (generation === saveGeneration.current) {
          setSaved(true);
        }
      },
    });
  };

  const clearSaveTimer = () => {
    if (saveTimer.current !== null) {
      window.clearTimeout(saveTimer.current);
      saveTimer.current = null;
    }
  };

  const update = <K extends keyof FormState>(key: K, value: FormState[K], immediate: boolean) => {
    const next = { ...formRef.current, [key]: value };
    formRef.current = next;
    setForm(next);
    setSaved(false);
    updateProfile.reset();
    clearSaveTimer();
    if (immediate) {
      persist(next);
      return;
    }
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
      onSubmit={(event) => event.preventDefault()}
      noValidate
      className="flex max-w-xl flex-col gap-4"
    >
      <label className={labelClass}>
        Цель
        <select
          className={selectClass}
          value={form.goal}
          onChange={(event) => update("goal", event.target.value, true)}
        >
          {GOAL_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <div className="grid grid-cols-2 gap-4">
        <label className={labelClass}>
          Рост, см
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.height}
            aria-invalid={errors.height ? true : undefined}
            aria-describedby={errors.height ? "height-error" : undefined}
            onChange={(event) => update("height", event.target.value, false)}
            onBlur={flushTextSave}
          />
          {errors.height && (
            <span id="height-error" className="text-sm font-normal text-red-600">
              {errors.height}
            </span>
          )}
        </label>

        <label className={labelClass}>
          Возраст, лет
          <input
            className={inputClass}
            inputMode="numeric"
            value={form.age}
            aria-invalid={errors.age ? true : undefined}
            aria-describedby={errors.age ? "age-error" : undefined}
            onChange={(event) => update("age", event.target.value, false)}
            onBlur={flushTextSave}
          />
          {errors.age && (
            <span id="age-error" className="text-sm font-normal text-red-600">
              {errors.age}
            </span>
          )}
        </label>
      </div>

      <label className={labelClass}>
        Пол
        <select
          className={selectClass}
          value={form.sex}
          onChange={(event) => update("sex", event.target.value, true)}
        >
          {SEX_OPTIONS.map((option) => (
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
          onChange={(event) =>
            update("weightUnit", event.target.value as FormState["weightUnit"], true)
          }
        >
          {UNIT_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className={labelClass}>
        Тема оформления
        <select
          className={selectClass}
          value={form.theme}
          onChange={(event) => update("theme", event.target.value as FormState["theme"], true)}
        >
          {THEME_OPTIONS.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <div className="flex flex-wrap items-center gap-3">
        {updateProfile.isPending && (
          <span role="status" className="text-sm text-slate-600 dark:text-slate-300">
            Сохраняем…
          </span>
        )}
        {saved && !updateProfile.isPending && (
          <span role="status" className="text-sm text-green-700 dark:text-green-400">
            Сохранено
          </span>
        )}
        {updateProfile.isError && (
          <span role="alert" className="text-sm text-red-600">
            {updateProfile.error.message}
          </span>
        )}
      </div>
    </form>
  );
}

const actionButton =
  "min-h-11 rounded-lg border border-slate-300 px-4 text-sm font-medium hover:bg-slate-100 disabled:opacity-50 dark:border-slate-700 dark:hover:bg-slate-800";

function isExportDocument(value: unknown): value is ExportDocument {
  return (
    typeof value === "object" &&
    value !== null &&
    "format_version" in value &&
    value.format_version === 1 &&
    "profile" in value &&
    "exercises" in value
  );
}

function DataSection() {
  const queryClient = useQueryClient();
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = (caught: unknown, fallback: string) => {
    setMessage(null);
    setError(caught instanceof Error ? caught.message : fallback);
  };

  const downloadJson = async () => {
    setBusy(true);
    setError(null);
    try {
      const document = await api.exportData();
      const blob = new Blob([JSON.stringify(document, null, 2)], { type: "application/json" });
      saveBlob(blob, backupFilename(document.exported_at));
      setMessage("Файл JSON сохранён");
    } catch (caught) {
      fail(caught, "Не удалось скачать экспорт");
    } finally {
      setBusy(false);
    }
  };

  const downloadCsv = async () => {
    setBusy(true);
    setError(null);
    try {
      const blob = await api.downloadWorkoutsCsv();
      saveBlob(blob, "workouts.csv");
      setMessage("Файл CSV сохранён");
    } catch (caught) {
      fail(caught, "Не удалось скачать CSV");
    } finally {
      setBusy(false);
    }
  };

  const importFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    const confirmed = window.confirm(
      "Импорт заменит упражнения, тренировки, план, журнал и подсказки по прогрессии этого аккаунта. Продолжить?",
    );
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const parsed: unknown = JSON.parse(await file.text());
      if (!isExportDocument(parsed)) {
        setMessage(null);
        setError("В файле нет данных экспорта");
        return;
      }
      await api.importData(parsed);
      await queryClient.invalidateQueries();
      setMessage("Данные заменены из файла");
    } catch (caught) {
      if (caught instanceof SyntaxError) {
        setMessage(null);
        setError("Файл не является JSON");
        return;
      }
      fail(caught, "Не удалось импортировать файл");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex max-w-xl flex-col gap-3 border-t border-slate-200 pt-4 dark:border-slate-800">
      <h2 className="text-lg font-semibold">Резервная копия</h2>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        JSON содержит все данные аккаунта. CSV — только записанные тренировки. Импорт заменяет
        текущие данные.
      </p>
      <div className="flex flex-wrap gap-3">
        <button type="button" className={actionButton} disabled={busy} onClick={() => void downloadJson()}>
          Скачать JSON
        </button>
        <button type="button" className={actionButton} disabled={busy} onClick={() => void downloadCsv()}>
          Скачать CSV
        </button>
        <label className={`${actionButton} inline-flex cursor-pointer items-center ${busy ? "opacity-50" : ""}`}>
          Импортировать JSON
          <input
            type="file"
            accept="application/json,.json"
            className="sr-only"
            disabled={busy}
            onChange={(event) => void importFile(event)}
          />
        </label>
      </div>
      {message && (
        <p role="status" className="text-sm text-green-700 dark:text-green-400">
          {message}
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  );
}

function AccountSection() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const handleDelete = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password.length < 8) {
      setError("Введите пароль от аккаунта");
      return;
    }
    const confirmed = window.confirm(
      "Аккаунт и все тренировки, план и журнал будут удалены без восстановления. Продолжить?",
    );
    if (!confirmed) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await api.deleteAccount(password);
      queryClient.setQueryData(ME_QUERY_KEY, null);
      queryClient.removeQueries({ predicate: (query) => query.queryKey[0] !== "auth" });
      navigate("/login", { replace: true });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Не удалось удалить аккаунт");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="flex max-w-xl flex-col gap-3 border-t border-slate-200 pt-4 dark:border-slate-800">
      <h2 className="text-lg font-semibold">Удаление аккаунта</h2>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Перед удалением скачайте JSON: восстановить аккаунт после этого нельзя. Выгрузка данных — в
        блоке «Резервная копия» выше.
      </p>
      <form onSubmit={(event) => void handleDelete(event)} noValidate className="flex flex-col gap-3">
        <label className={labelClass}>
          Пароль для удаления
          <input
            type="password"
            autoComplete="current-password"
            className={inputClass}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <button
          type="submit"
          disabled={busy}
          className="min-h-11 self-start rounded-lg bg-red-700 px-4 text-sm font-medium text-white hover:bg-red-800 disabled:opacity-50"
        >
          {busy ? "Удаляем…" : "Удалить аккаунт"}
        </button>
        {error && (
          <p role="alert" className="text-sm text-red-600">
            {error}
          </p>
        )}
      </form>
    </section>
  );
}

export function SettingsPage() {
  const { data: profile, isPending, isError } = useProfile();

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-2xl font-semibold">Настройки</h1>
      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
      {isError && <p className="text-red-600">Не удалось загрузить настройки. Обновите страницу.</p>}
      {profile && <ProfileForm profile={profile} />}
      <DataSection />
      <AccountSection />
    </div>
  );
}
