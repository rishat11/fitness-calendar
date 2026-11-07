import { useEffect, useRef, useState } from "react";
import { useMutationState } from "@tanstack/react-query";
import {
  DndContext,
  KeyboardSensor,
  PointerSensor,
  TouchSensor,
  useSensor,
  useSensors,
  type DragEndEvent,
} from "@dnd-kit/core";
import { DayCell } from "../components/calendar/DayCell";
import { AddEntryPanel } from "../components/calendar/AddEntryPanel";
import { EntryPanel } from "../components/calendar/EntryPanel";
import {
  WEEKDAY_LABELS,
  addDays,
  addMonths,
  formatMonthTitle,
  formatWeekTitle,
  isInMonth,
  monthGrid,
  monthOf,
  todayIso,
  weekDates,
  weekdayIndex,
} from "../features/calendar/dates";
import { type PlanEntry, type PlanShiftChange, type PlanShiftResult } from "../api/client";
import { dropMove } from "../features/calendar/drag";
import {
  usePlanRange,
  usePlanShiftHistory,
  useUndoPlanShift,
  useUpdatePlanEntry,
} from "../features/plan/usePlan";
import { useWorkouts } from "../features/workouts/useWorkouts";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";

type View = "month" | "week";

function withShiftChange(entry: PlanEntry | null, changes: PlanShiftChange[]): PlanEntry | null {
  if (!entry) return entry;
  const change = changes.find((item) => item.id === entry.id);
  if (!change) return entry;
  return { ...entry, date: change.date_after, status: change.status_after };
}

export function CalendarPage() {
  const [view, setView] = useState<View>("month");
  const [anchor, setAnchor] = useState(todayIso);
  const [selectedDate, setSelectedDate] = useState(todayIso);
  // Храним саму запись, а не только id: после переноса за пределы диапазона её нет в загруженных данных.
  const [selectedSnapshot, setSelectedSnapshot] = useState<PlanEntry | null>(null);

  const today = todayIso();
  const { year, month } = monthOf(anchor);
  const days = view === "month" ? monthGrid(year, month) : weekDates(anchor);
  const rangeStart = days[0];
  const rangeEnd = days[days.length - 1];

  const { data: entries, isPending, isError } = usePlanRange(rangeStart, rangeEnd);
  const { data: workouts } = useWorkouts();
  const { data: shiftHistory } = usePlanShiftHistory();
  const move = useUpdatePlanEntry();
  const undoShift = useUndoPlanShift();
  const [shiftToast, setShiftToast] = useState(false);
  const seenShift = useRef(0);
  const lastApply = useMutationState({
    filters: { mutationKey: ["plan", "shift", "apply"] },
    select: (mutation) => ({
      submittedAt: mutation.state.submittedAt,
      status: mutation.state.status,
      data: mutation.state.data as PlanShiftResult | undefined,
    }),
  }).at(-1);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(TouchSensor, { activationConstraint: { delay: 200, tolerance: 6 } }),
    // Клавиатура: Пробел или Enter поднимает карточку, стрелки двигают по дням, Пробел опускает.
    useSensor(KeyboardSensor),
  );

  const entriesByDate = new Map<string, PlanEntry[]>();
  for (const entry of entries ?? []) {
    const list = entriesByDate.get(entry.date) ?? [];
    list.push(entry);
    entriesByDate.set(entry.date, list);
  }

  // Свежую версию берём из загруженного диапазона; если запись вне его, остаётся последняя версия из ответа сервера.
  const selectedEntry = selectedSnapshot
    ? (entries?.find((entry) => entry.id === selectedSnapshot.id) ?? selectedSnapshot)
    : null;

  const shift = (delta: number) => {
    setAnchor((current) => (view === "month" ? addMonths(current, delta) : addDays(current, delta * 7)));
  };

  const goToToday = () => {
    const today = todayIso();
    setAnchor(today);
    setSelectedDate(today);
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const drop = dropMove(event);
    if (drop) move.mutate({ id: drop.id, body: { date: drop.date } });
  };

  useEffect(() => {
    if (!lastApply || lastApply.status !== "success" || !lastApply.data?.applied) return;
    if (lastApply.submittedAt === seenShift.current) return;
    seenShift.current = lastApply.submittedAt;
    setShiftToast(true);
    setSelectedSnapshot((current) => withShiftChange(current, lastApply.data?.changes ?? []));
  }, [lastApply]);

  const handleUndoShift = () => {
    undoShift.mutate(undefined, {
      onSuccess: (result) => {
        setShiftToast(false);
        setSelectedSnapshot((current) => withShiftChange(current, result.changes));
      },
    });
  };

  const title = view === "month" ? formatMonthTitle(year, month) : formatWeekTitle(days);

  return (
    <div className="flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Календарь</h1>
        <div className="flex flex-wrap items-center gap-2">
          <div role="group" aria-label="Вид календаря" className="flex gap-1">
            {(["month", "week"] as const).map((option) => (
              <button
                key={option}
                type="button"
                aria-pressed={view === option}
                onClick={() => setView(option)}
                className={`${buttonClass} border border-slate-300 dark:border-slate-700 ${
                  view === option ? "bg-slate-200 font-semibold dark:bg-slate-800" : ""
                }`}
              >
                {option === "month" ? "Месяц" : "Неделя"}
              </button>
            ))}
          </div>
          <button type="button" className={buttonClass} onClick={() => shift(-1)} aria-label="Назад">
            ←
          </button>
          <button type="button" className={buttonClass} onClick={goToToday}>
            Сегодня
          </button>
          <button type="button" className={buttonClass} onClick={() => shift(1)} aria-label="Вперёд">
            →
          </button>
          {(shiftHistory?.length ?? 0) > 0 && (
            <button
              type="button"
              className={buttonClass}
              disabled={undoShift.isPending}
              onClick={handleUndoShift}
            >
              Отменить сдвиг
            </button>
          )}
        </div>
      </div>

      {shiftToast && (
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
            onClick={handleUndoShift}
          >
            Отменить
          </button>
        </div>
      )}

      <h2 className="text-lg font-medium">{title}</h2>

      {(move.isError || undoShift.isError) && (
        <p role="alert" className="text-sm text-red-600">
          {(move.error ?? undoShift.error)?.message}
        </p>
      )}
      {isError && <p className="text-red-600">Не удалось загрузить план. Обновите страницу.</p>}
      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}

      <DndContext sensors={sensors} onDragEnd={handleDragEnd}>
        <div className="flex flex-col gap-2" aria-label="Дни календаря">
          {view === "month" && (
            <div className="grid grid-cols-7 gap-1 text-center text-xs text-slate-600 dark:text-slate-300">
              {WEEKDAY_LABELS.map((label) => (
                <span key={label}>{label}</span>
              ))}
            </div>
          )}
          <div
            className={
              view === "month" ? "grid grid-cols-7 gap-1" : "grid grid-cols-1 gap-2 md:grid-cols-7"
            }
          >
            {days.map((iso) => (
              <DayCell
                key={iso}
                iso={iso}
                inMonth={view === "week" || isInMonth(iso, year, month)}
                isToday={iso === today}
                isSelected={iso === selectedDate}
                entries={entriesByDate.get(iso) ?? []}
                selectedEntryId={selectedEntry?.id ?? null}
                compact={view === "month"}
                weekdayLabel={view === "week" ? WEEKDAY_LABELS[weekdayIndex(iso)] : null}
                onSelectDay={setSelectedDate}
                onSelectEntry={(entry) => {
                  setSelectedSnapshot(entry);
                  setSelectedDate(entry.date);
                }}
              />
            ))}
          </div>
        </div>
      </DndContext>

      <p className="text-sm text-slate-600 dark:text-slate-300">
        Перетащите тренировку на другой день или выберите её, чтобы перенести через дату.
      </p>

      {selectedEntry && (
        <EntryPanel
          key={`${selectedEntry.id}-${selectedEntry.date}`}
          entry={selectedEntry}
          onClose={() => setSelectedSnapshot(null)}
          onUpdated={setSelectedSnapshot}
          onShifted={(changes) => {
            setShiftToast(true);
            setSelectedSnapshot((current) => withShiftChange(current, changes));
          }}
        />
      )}

      <AddEntryPanel
        date={selectedDate}
        workouts={workouts}
        onDateChange={setSelectedDate}
      />
    </div>
  );
}
