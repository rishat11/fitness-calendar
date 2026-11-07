import { useState, type FormEvent } from "react";
import { type Workout } from "../../api/client";
import { WEEKDAY_LABELS, formatLongDate } from "../../features/calendar/dates";
import { useAddPlanCycle, useAddPlanEntry } from "../../features/plan/usePlan";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";
const inputClass =
  "min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const sectionClass = "flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800";

const MAX_WEEKS = 52;

type AddEntryPanelProps = {
  date: string;
  /** undefined, пока библиотека загружается. */
  workouts: Workout[] | undefined;
  onDateChange: (iso: string) => void;
};

/** Постановка на день: тренировка из библиотеки, с нуля, отдых и повторяющийся цикл. */
export function AddEntryPanel({ date, workouts, onDateChange }: AddEntryPanelProps) {
  const addEntry = useAddPlanEntry();
  const addCycle = useAddPlanCycle();
  const [templateId, setTemplateId] = useState("");
  const [name, setName] = useState("");
  const [weekdays, setWeekdays] = useState<number[]>([]);
  const [weeks, setWeeks] = useState("8");
  const [cycleMessage, setCycleMessage] = useState<string | null>(null);
  const [nameError, setNameError] = useState<string | null>(null);

  const library = workouts ?? [];
  const hasLibrary = library.length > 0;
  const weeksValue = Number(weeks);
  const weeksValid = Number.isInteger(weeksValue) && weeksValue >= 1 && weeksValue <= MAX_WEEKS;

  const addFromLibrary = () => {
    addEntry.mutate({ date, kind: "workout", template_id: templateId });
  };

  const addFromScratch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "") {
      setNameError("Укажите название");
      return;
    }
    setNameError(null);
    addEntry.mutate({ date, kind: "workout", name: trimmed }, { onSuccess: () => setName("") });
  };

  const addRest = () => {
    addEntry.mutate({ date, kind: "rest" });
  };

  const toggleWeekday = (index: number) => {
    setWeekdays((current) =>
      current.includes(index) ? current.filter((value) => value !== index) : [...current, index].sort(),
    );
  };

  const addCycleEntries = () => {
    setCycleMessage(null);
    addCycle.mutate(
      { template_id: templateId, start_date: date, weekdays, weeks: weeksValue },
      {
        onSuccess: (entries) => setCycleMessage(`Создано тренировок: ${entries.length}`),
      },
    );
  };

  return (
    <section aria-label="Добавить в план" className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Дата
          <input
            type="date"
            aria-label="Дата записи"
            className={inputClass}
            value={date}
            onChange={(event) => onDateChange(event.target.value)}
          />
        </label>
        <p className="min-h-11 self-center text-sm text-slate-600 dark:text-slate-300">
          {formatLongDate(date)}
        </p>
      </div>

      <div className={sectionClass}>
        <h2 className="text-base font-semibold">Из библиотеки</h2>
        {workouts === undefined ? (
          <p className="text-sm text-slate-600 dark:text-slate-300">Загрузка библиотеки…</p>
        ) : hasLibrary ? (
          <div className="flex flex-wrap items-end gap-2">
            <label className="flex flex-col gap-1 text-sm font-medium">
              Тренировка из библиотеки
              <select
                aria-label="Тренировка из библиотеки"
                className={inputClass}
                value={templateId}
                onChange={(event) => setTemplateId(event.target.value)}
              >
                <option value="">Выберите тренировку</option>
                {library.map((workout) => (
                  <option key={workout.id} value={workout.id}>
                    {workout.name}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              className={primaryButtonClass}
              disabled={templateId === "" || addEntry.isPending}
              onClick={addFromLibrary}
            >
              Поставить на день
            </button>
          </div>
        ) : (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            В библиотеке пока нет тренировок. Создайте их в разделе «Тренировки».
          </p>
        )}
      </div>

      <div className={sectionClass}>
        <h2 className="text-base font-semibold">С нуля и отдых</h2>
        <form onSubmit={addFromScratch} noValidate aria-label="Тренировка с нуля" className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Название
            <input
              aria-label="Название тренировки"
              className={inputClass}
              value={name}
              aria-invalid={nameError ? true : undefined}
              onChange={(event) => setName(event.target.value)}
            />
          </label>
          <button type="submit" className={primaryButtonClass} disabled={addEntry.isPending}>
            Добавить с нуля
          </button>
          <button type="button" className={buttonClass} disabled={addEntry.isPending} onClick={addRest}>
            Отметить отдых
          </button>
        </form>
        {nameError && (
          <p role="alert" className="text-sm text-red-600">
            {nameError}
          </p>
        )}
        {addEntry.isError && (
          <p role="alert" className="text-sm text-red-600">
            {addEntry.error.message}
          </p>
        )}
      </div>

      <div className={sectionClass}>
        <h2 className="text-base font-semibold">Повтор по дням недели</h2>
        <fieldset className="flex flex-col gap-3">
          <legend className="sr-only">Дни недели</legend>
          <div className="flex flex-wrap gap-2">
            {WEEKDAY_LABELS.map((label, index) => (
              <label
                key={label}
                className={`flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-1 rounded-lg border px-2 text-sm ${
                  weekdays.includes(index)
                    ? "border-slate-900 bg-slate-900 text-white dark:border-slate-100 dark:bg-slate-100 dark:text-slate-900"
                    : "border-slate-300 dark:border-slate-700"
                }`}
              >
                <input
                  type="checkbox"
                  className="sr-only"
                  aria-label={label}
                  checked={weekdays.includes(index)}
                  onChange={() => toggleWeekday(index)}
                />
                {label}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Недель
            <input
              inputMode="numeric"
              aria-label="Количество недель"
              className={`${inputClass} w-24`}
              value={weeks}
              onChange={(event) => setWeeks(event.target.value)}
            />
          </label>
          <button
            type="button"
            className={primaryButtonClass}
            disabled={templateId === "" || weekdays.length === 0 || !weeksValid || addCycle.isPending}
            onClick={addCycleEntries}
          >
            Создать цикл
          </button>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Цикл берёт тренировку, выбранную выше в блоке «Из библиотеки», и начинается с даты записи.
        </p>
        {cycleMessage && (
          <p role="status" className="text-sm text-slate-600 dark:text-slate-300">
            {cycleMessage}
          </p>
        )}
        {addCycle.isError && (
          <p role="alert" className="text-sm text-red-600">
            {addCycle.error.message}
          </p>
        )}
      </div>
    </section>
  );
}
