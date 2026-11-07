import { useDraggable } from "@dnd-kit/core";
import { type PlanEntry } from "../../api/client";
import { entryTitle, statusLabel } from "../../features/plan/labels";

type EntryCardProps = {
  entry: PlanEntry;
  selected: boolean;
  /** Месячная сетка: на телефоне вместо текста показываем точку, полное название — от sm. */
  compact: boolean;
  onSelect: () => void;
};

/** Карточка записи плана. Перетаскивается, если запись запланирована или это день отдыха. */
export function EntryCard({ entry, selected, compact, onSelect }: EntryCardProps) {
  const canDrag = entry.kind === "rest" || entry.status === "planned";
  const { attributes, listeners, setNodeRef, transform, isDragging } = useDraggable({
    id: `entry-${entry.id}`,
    data: { entry },
    disabled: !canDrag,
  });

  const title = entryTitle(entry);
  const isRest = entry.kind === "rest";
  // Статус показываем только у тренировок, не у отдыха (там статуса нет).
  const details = [
    !isRest && entry.status && entry.status !== "planned" && statusLabel(entry.status),
    entry.is_fixed && "фикс.",
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <button
      type="button"
      ref={setNodeRef}
      {...listeners}
      {...attributes}
      onClick={onSelect}
      aria-pressed={selected}
      aria-label={compact ? `${title}${details ? `, ${details}` : ""}` : undefined}
      title={title}
      style={transform ? { transform: `translate3d(${transform.x}px, ${transform.y}px, 0)` } : undefined}
      className={`flex w-full min-w-0 rounded-md border text-left text-xs sm:text-sm ${
        compact
          ? "min-h-11 items-center justify-center p-0.5 sm:flex-col sm:items-start sm:justify-start sm:px-2 sm:py-1"
          : "min-h-11 flex-col px-2 py-1"
      } ${
        isRest
          ? "border-dashed border-slate-300 text-slate-600 dark:border-slate-700 dark:text-slate-300"
          : "border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
      } ${selected ? "ring-2 ring-slate-900 dark:ring-slate-100" : ""} ${
        canDrag ? "cursor-grab touch-manipulation" : "cursor-pointer"
      } ${isDragging ? "relative z-10 opacity-80 shadow-lg" : ""}`}
    >
      {compact && (
        <span
          aria-hidden="true"
          className={`size-2 shrink-0 rounded-full sm:hidden ${
            isRest ? "border border-slate-400" : "bg-slate-900 dark:bg-slate-100"
          }`}
        />
      )}
      <span className={`w-full truncate font-medium ${compact ? "hidden sm:block" : ""}`}>{title}</span>
      {details && (
        <span
          className={`w-full truncate text-[11px] text-slate-600 dark:text-slate-300 ${
            compact ? "hidden sm:block" : ""
          }`}
        >
          {details}
        </span>
      )}
    </button>
  );
}
