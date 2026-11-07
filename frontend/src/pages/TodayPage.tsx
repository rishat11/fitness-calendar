import { useState } from "react";
import { Link } from "react-router-dom";
import { type PlanShiftChange, type TodayEntry } from "../api/client";
import { PlanShiftPanel } from "../components/calendar/PlanShiftPanel";
import { useMe } from "../features/auth/useAuth";
import { hideReminder, reminderHidden } from "../features/transfer/reminder";
import { hideInbodyReminder, inbodyReminderHidden, scanReminderDue } from "../features/inbody/reminder";
import { useInbodyScans } from "../features/inbody/useInbody";
import { parseIsoDate, todayIso } from "../features/calendar/dates";
import { canShift, statusLabel } from "../features/plan/labels";
import { usePlanShiftHistory, useToday, useUndoPlanShift } from "../features/plan/usePlan";
import { ProgressionHintCard } from "../features/progression/ProgressionHint";

const dateFormatter = new Intl.DateTimeFormat("ru-RU", {
  weekday: "long",
  day: "numeric",
  month: "long",
});

const buttonClass =
  "min-h-11 rounded-xl px-3 text-sm font-medium text-stone-700 transition hover:bg-stone-200/70 disabled:opacity-50 dark:text-stone-200 dark:hover:bg-white/10";
const primaryButtonClass = "btn-primary";

function openLabel(entry: TodayEntry): string {
  return entry.log_state === "open" ? "Продолжить" : "Открыть";
}

export function TodayPage() {
  const { data: user } = useMe();
  // Дата считается при каждом рендере, чтобы не устаревать при открытии вкладки через полночь.
  const today = todayIso();
  const todayLabel = dateFormatter.format(parseIsoDate(today));
  const { data, isPending, isError } = useToday(today);
  const { data: shiftHistory } = usePlanShiftHistory();
  const undoShift = useUndoPlanShift();
  const [shiftOpen, setShiftOpen] = useState(false);
  const [shiftId, setShiftId] = useState<string | null>(null);
  const [shiftNotice, setShiftNotice] = useState(false);
  const [reminderDismissed, setReminderDismissed] = useState(false);
  const [inbodyDismissed, setInbodyDismissed] = useState(false);
  const scans = useInbodyScans();
  const showReminder = Boolean(
    data?.export_reminder && user && !reminderDismissed && !reminderHidden(user.id),
  );
  const latestScan = scans.data && scans.data.length > 0 ? scans.data[scans.data.length - 1].measured_on : null;
  const showInbodyReminder = Boolean(
    scans.isSuccess &&
      user &&
      !inbodyDismissed &&
      !inbodyReminderHidden(user.id) &&
      scanReminderDue(latestScan, today),
  );

  const entries = data?.entries ?? [];
  const workouts = entries.filter((entry) => entry.kind === "workout");
  const rest = entries.find((entry) => entry.kind === "rest");
  const movable = entries.filter((entry) => canShift(entry));
  const shiftEntry = movable.find((entry) => entry.id === shiftId) ?? movable[0] ?? null;

  const handleShifted = (changes: PlanShiftChange[]) => {
    setShiftOpen(false);
    setShiftNotice(changes.length > 0);
  };

  return (
    <div className="flex max-w-3xl flex-col gap-8">
      <header className="flex flex-col gap-1">
        <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700 capitalize dark:text-emerald-400">
          {todayLabel}
        </p>
        <h1 className="text-3xl font-bold tracking-tight">Привет, {user?.email}</h1>
      </header>

      {showReminder && user && (
        <aside
          role="status"
          aria-label="Резервная копия"
          className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <p>Пора обновить резервную копию. Скачайте экспорт в настройках.</p>
          <div className="flex flex-wrap gap-2">
            <Link to="/settings" className={primaryButtonClass}>
              Открыть настройки
            </Link>
            <button
              type="button"
              className={buttonClass}
              onClick={() => {
                hideReminder(user.id);
                setReminderDismissed(true);
              }}
            >
              Не сейчас
            </button>
          </div>
        </aside>
      )}

      {showInbodyReminder && user && (
        <aside
          role="status"
          aria-label="Замер InBody"
          className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <p>
            {latestScan == null
              ? "Замера InBody ещё нет. Сделайте его и вносите лист вручную."
              : "Пора повторить замер InBody. Прошло уже две недели."}
            {" "}
            Вывод строится по нескольким замерам.
          </p>
          <div className="flex flex-wrap gap-2">
            <Link to="/inbody" className={primaryButtonClass}>
              Открыть InBody
            </Link>
            <button
              type="button"
              className={buttonClass}
              onClick={() => {
                hideInbodyReminder(user.id);
                setInbodyDismissed(true);
              }}
            >
              Не сейчас
            </button>
          </div>
        </aside>
      )}

      <section className="flex flex-col gap-3" aria-label="Тренировка дня">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-400">Тренировка дня</h2>
        {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
        {isError && (
          <p role="alert" className="text-red-600">
            Не удалось загрузить день. Обновите страницу.
          </p>
        )}
        {!isPending && !isError && workouts.length === 0 && !rest && (
          <article className="card p-6">
            <p className="text-stone-600 dark:text-stone-300">На сегодня ничего не запланировано.</p>
            <Link to="/calendar" className={`${primaryButtonClass} mt-3`}>
              Открыть календарь
            </Link>
          </article>
        )}
        {rest && (
          <article className="card p-6">
            <h3 className="font-semibold">День отдыха</h3>
            <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">Тренировки на этот день нет.</p>
          </article>
        )}
        {workouts.map((entry) => (
          <article
            key={entry.id}
            className="card flex flex-col gap-4 border-l-4 border-l-emerald-500 p-6"
          >
            <div>
              <h3 className="font-semibold">{entry.name ?? "Тренировка"}</h3>
              {entry.status && (
                <p className="text-sm text-slate-600 dark:text-slate-300">{statusLabel(entry.status)}</p>
              )}
            </div>
            {entry.items.length > 0 && (
              <ul className="flex flex-col gap-3">
                {entry.items.map((item) => (
                  <li key={item.position} className="flex flex-col gap-2">
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      {item.exercise.name}
                      <span> · подходов: {item.sets.length}</span>
                    </p>
                    <ProgressionHintCard exerciseId={item.exercise.exercise_id} />
                  </li>
                ))}
              </ul>
            )}
            <Link to={`/log/${entry.id}`} className={`${primaryButtonClass} self-start`}>
              {openLabel(entry)}
            </Link>
          </article>
        ))}
      </section>

      <section className="flex flex-col gap-3" aria-label="Сдвиг плана">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-stone-500 dark:text-stone-400">Сдвиг плана</h2>
        {shiftNotice && (
          <div
            role="status"
            aria-label="План изменён"
            className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700"
          >
            План изменён.
            <button
              type="button"
              className={buttonClass}
              disabled={undoShift.isPending}
              onClick={() =>
                undoShift.mutate(undefined, {
                  onSuccess: () => setShiftNotice(false),
                })
              }
            >
              Отменить
            </button>
          </div>
        )}
        {(shiftHistory?.length ?? 0) > 0 && !shiftNotice && (
          <button
            type="button"
            className={`${buttonClass} self-start`}
            disabled={undoShift.isPending}
            onClick={() => undoShift.mutate()}
          >
            Отменить сдвиг
          </button>
        )}
        {undoShift.isError && (
          <p role="alert" className="text-sm text-red-600">
            {undoShift.error.message}
          </p>
        )}
        <button
          type="button"
          className={`${buttonClass} self-start border border-stone-300 dark:border-white/15`}
          aria-expanded={shiftOpen}
          disabled={shiftEntry == null}
          onClick={() => setShiftOpen((open) => !open)}
        >
          Сдвинуть план
        </button>
        {shiftEntry == null && !isPending && !isError && (
          <p className="text-sm text-slate-600 dark:text-slate-300">
            Сдвигать можно запланированную тренировку или день отдыха, если они не зафиксированы.
          </p>
        )}
        {shiftOpen && movable.length > 1 && (
          <label className="flex max-w-sm flex-col gap-1 text-sm font-medium">
            Какую запись сдвинуть
            <select
              className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900"
              value={shiftEntry?.id ?? ""}
              onChange={(event) => setShiftId(event.target.value)}
            >
              {movable.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.kind === "rest" ? "День отдыха" : (entry.name ?? "Тренировка")}
                </option>
              ))}
            </select>
          </label>
        )}
        {shiftOpen && shiftEntry && (
          <PlanShiftPanel
            key={shiftEntry.id}
            entry={shiftEntry}
            onApplied={handleShifted}
          />
        )}
      </section>
    </div>
  );
}
