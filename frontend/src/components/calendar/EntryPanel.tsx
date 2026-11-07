import { useState } from "react";
import { Link } from "react-router-dom";
import { type PlanEntry, type PlanShiftChange } from "../../api/client";
import { PlanShiftPanel } from "./PlanShiftPanel";
import { formatLongDate } from "../../features/calendar/dates";
import { STATUS_OPTIONS, canChangeStatus, entryTitle } from "../../features/plan/labels";
import { useDeletePlanEntry, useUpdatePlanEntry } from "../../features/plan/usePlan";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";
const inputClass =
  "min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";

type EntryPanelProps = {
  entry: PlanEntry;
  onClose: () => void;
  /** Вызывается с актуальной записью из ответа сервера, чтобы родитель помнил её даже вне текущего диапазона. */
  onUpdated?: (entry: PlanEntry) => void;
  onShifted?: (changes: PlanShiftChange[]) => void;
};

/** Действия над записью: статус, перенос на дату, фиксация, удаление. */
export function EntryPanel({ entry, onClose, onUpdated, onShifted }: EntryPanelProps) {
  const update = useUpdatePlanEntry();
  const remove = useDeletePlanEntry();
  const [newDate, setNewDate] = useState(entry.date);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const isRest = entry.kind === "rest";
  const busy = update.isPending || remove.isPending;
  // День отдыха статуса не имеет и переносится свободно; тренировка — только в статусе «запланирована».
  const canMove = (isRest || entry.status === "planned") && newDate !== entry.date;
  const handleUpdated = (updated: PlanEntry) => onUpdated?.(updated);

  const handleMove = () => {
    update.mutate({ id: entry.id, body: { date: newDate } }, { onSuccess: handleUpdated });
  };

  return (
    <section
      aria-label={`Запись: ${entryTitle(entry)}`}
      className="flex flex-col gap-4 rounded-xl border border-slate-200 p-4 dark:border-slate-800"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col">
          <h2 className="text-lg font-semibold">{entryTitle(entry)}</h2>
          <p className="text-sm text-slate-600 dark:text-slate-300">{formatLongDate(entry.date)}</p>
        </div>
        <button type="button" className={buttonClass} onClick={onClose}>
          Закрыть
        </button>
      </div>

      {!isRest && (
        <Link to={`/log/${entry.id}`} className={`${primaryButtonClass} inline-flex items-center justify-center`}>
          Записать тренировку
        </Link>
      )}

      {!isRest && entry.items.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm text-slate-600 dark:text-slate-300">
          {entry.items.map((item) => (
            <li key={item.position}>
              {item.exercise.name}
              <span className="text-slate-600 dark:text-slate-300"> · подходов: {item.sets.length}</span>
            </li>
          ))}
        </ul>
      )}

      {!isRest && (
        <div role="group" aria-label="Статус" className="flex flex-wrap gap-2">
          {STATUS_OPTIONS.map((option) => (
            <button
              key={option.value}
              type="button"
              aria-pressed={entry.status === option.value}
              disabled={busy || !canChangeStatus(entry.status ?? "planned", option.value)}
              onClick={() =>
                update.mutate({ id: entry.id, body: { status: option.value } }, { onSuccess: handleUpdated })
              }
              className={`${buttonClass} border border-slate-300 dark:border-slate-700 ${
                entry.status === option.value ? "bg-slate-200 font-semibold dark:bg-slate-800" : ""
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      )}

      <div className="flex flex-wrap items-end gap-2">
        <label className="flex flex-col gap-1 text-sm font-medium">
          Новая дата
          <input
            type="date"
            aria-label="Новая дата"
            className={inputClass}
            value={newDate}
            onChange={(event) => setNewDate(event.target.value)}
          />
        </label>
        <button type="button" className={primaryButtonClass} disabled={!canMove || busy} onClick={handleMove}>
          Перенести
        </button>
        {entry.status !== "planned" && !isRest && (
          <span className="text-sm text-slate-600 dark:text-slate-300">
            Перенос доступен только для запланированных записей
          </span>
        )}
      </div>

      <label className="flex min-h-11 items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-5"
          checked={entry.is_fixed}
          disabled={busy}
          onChange={(event) =>
            update.mutate(
              { id: entry.id, body: { is_fixed: event.target.checked } },
              { onSuccess: handleUpdated },
            )
          }
        />
        Фиксированная: не двигается при сдвиге плана
      </label>

      <PlanShiftPanel entry={entry} onApplied={(changes) => onShifted?.(changes)} />

      <div className="flex flex-wrap items-center gap-2">
        {confirmingDelete ? (
          <>
            <span className="text-sm">Удалить запись из плана?</span>
            <button
              type="button"
              className={`${buttonClass} text-red-600`}
              disabled={busy}
              onClick={() => remove.mutate(entry.id, { onSuccess: onClose })}
            >
              Удалить
            </button>
            <button type="button" className={buttonClass} onClick={() => setConfirmingDelete(false)}>
              Отмена
            </button>
          </>
        ) : (
          <button
            type="button"
            className={`${buttonClass} text-red-600`}
            disabled={busy}
            onClick={() => setConfirmingDelete(true)}
          >
            Удалить из плана
          </button>
        )}
      </div>

      {(update.isError || remove.isError) && (
        <p role="alert" className="text-sm text-red-600">
          {(update.error ?? remove.error)?.message}
        </p>
      )}
    </section>
  );
}
