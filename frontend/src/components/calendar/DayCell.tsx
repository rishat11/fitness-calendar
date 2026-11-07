import { useDroppable } from "@dnd-kit/core";
import { type PlanEntry } from "../../api/client";
import { formatLongDate, parseIsoDate } from "../../features/calendar/dates";
import { EntryCard } from "./EntryCard";

type DayCellProps = {
  iso: string;
  inMonth: boolean;
  isToday: boolean;
  isSelected: boolean;
  entries: PlanEntry[];
  selectedEntryId: string | null;
  compact: boolean;
  /** В недельном виде название дня показываем в самой ячейке; в месячном — в шапке сетки. */
  weekdayLabel: string | null;
  onSelectDay: (iso: string) => void;
  onSelectEntry: (entry: PlanEntry) => void;
};

/** Ячейка дня: зона сброса для перетаскивания и список записей. */
export function DayCell({
  iso,
  inMonth,
  isToday,
  isSelected,
  entries,
  selectedEntryId,
  compact,
  weekdayLabel,
  onSelectDay,
  onSelectEntry,
}: DayCellProps) {
  const { setNodeRef, isOver } = useDroppable({ id: iso });
  const dayNumber = parseIsoDate(iso).getDate();

  return (
    <div
      ref={setNodeRef}
      data-date={iso}
      className={`flex min-w-0 flex-col gap-1 rounded-lg border p-1 sm:p-2 ${
        compact ? "min-h-24" : "min-h-16 md:min-h-40"
      } ${
        isOver
          ? "border-slate-900 bg-slate-100 dark:border-slate-100 dark:bg-slate-800"
          : "border-slate-200 dark:border-slate-800"
      } ${inMonth ? "" : "opacity-50"}`}
    >
      <div className="flex items-center gap-2">
        {/* Кнопка 44×44 px для касания; видимый круг рисует внутренний span. */}
        <button
          type="button"
          onClick={() => onSelectDay(iso)}
          aria-label={`Выбрать день: ${formatLongDate(iso)}`}
          aria-pressed={isSelected}
          className="flex size-11 shrink-0 items-center justify-center text-sm font-medium"
        >
          <span
            className={`flex size-8 items-center justify-center rounded-full ${
              isToday ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : ""
            } ${isSelected && !isToday ? "ring-2 ring-slate-900 dark:ring-slate-100" : ""}`}
          >
            {dayNumber}
          </span>
        </button>
        {weekdayLabel && <span className="text-sm text-slate-600 dark:text-slate-300">{weekdayLabel}</span>}
      </div>
      {entries.map((entry) => (
        <EntryCard
          key={entry.id}
          entry={entry}
          selected={entry.id === selectedEntryId}
          compact={compact}
          onSelect={() => onSelectEntry(entry)}
        />
      ))}
    </div>
  );
}
