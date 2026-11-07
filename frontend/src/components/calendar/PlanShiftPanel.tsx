import { useState } from "react";
import {
  type PlanEntry,
  type PlanShiftChange,
  type PlanShiftPreview,
  type PlanShiftRequest,
} from "../../api/client";
import { formatLongDate } from "../../features/calendar/dates";
import { canShift, statusLabel } from "../../features/plan/labels";
import { useApplyPlanShift, usePreviewPlanShift } from "../../features/plan/usePlan";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";
const inputClass =
  "min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";

type PlanShiftPanelProps = {
  entry: PlanEntry;
  swapCandidates: PlanEntry[];
  onApplied: (changes: PlanShiftChange[]) => void;
};

type PreviewState = {
  request: PlanShiftRequest;
  result: PlanShiftPreview;
};

function changeText(change: PlanShiftChange): string {
  const title = change.kind === "rest" ? "Отдых" : (change.name ?? "Тренировка");
  const when = `${formatLongDate(change.date_before)} → ${formatLongDate(change.date_after)}`;
  if (change.status_before !== change.status_after && change.status_after) {
    return `${title}: ${when}, ${statusLabel(change.status_after)}`;
  }
  return `${title}: ${when}`;
}

function conflictText(result: PlanShiftPreview): string {
  if (result.conflicts.some((conflict) => conflict.reason === "blocked")) {
    return "Запись попадает на день, который нельзя совместить. Сдвиньте цепочку дальше или отмените.";
  }
  return "Тренировка попадает на занятый день. Можно сдвинуть цепочку дальше, оставить две тренировки в один день или отменить.";
}

/** Меню сдвига: предпросмотр «было, станет», варианты конфликта и применение. */
export function PlanShiftPanel({ entry, swapCandidates, onApplied }: PlanShiftPanelProps) {
  const previewShift = usePreviewPlanShift();
  const applyShift = useApplyPlanShift();
  const [days, setDays] = useState("1");
  const [otherId, setOtherId] = useState("");
  const [preview, setPreview] = useState<PreviewState | null>(null);
  const parsedDays = Number(days);
  const daysValid = Number.isInteger(parsedDays) && parsedDays !== 0 && Math.abs(parsedDays) <= 366;
  const movable = canShift(entry);
  const canSkip = entry.kind === "workout" && entry.status === "planned";
  const canSwap = movable && entry.kind === "workout" && otherId !== "";
  const busy = previewShift.isPending || applyShift.isPending;
  const error = previewShift.error ?? applyShift.error;

  const runPreview = (request: PlanShiftRequest) => {
    previewShift.mutate(request, {
      onSuccess: (result) => setPreview({ request, result }),
    });
  };

  const shiftRequest = (operation: "shift_following" | "shift_only"): PlanShiftRequest => ({
    operation,
    entry_id: entry.id,
    days: parsedDays,
  });

  const chooseResolution = (resolution: "cascade" | "stack") => {
    if (!preview) return;
    runPreview({ ...preview.request, resolution });
  };

  const apply = () => {
    if (!preview || preview.result.conflicts.length > 0) return;
    applyShift.mutate(preview.request, {
      onSuccess: (result) => {
        if (result.applied) onApplied(result.changes);
        setPreview(null);
      },
    });
  };

  return (
    <div className="flex flex-col gap-3" aria-label="Сдвиг плана">
      <h3 className="text-sm font-semibold">Сдвиг плана</h3>
      <label className="flex flex-col gap-1 text-sm font-medium">
        На сколько дней
        <input
          type="number"
          inputMode="numeric"
          min={-366}
          max={366}
          className={`${inputClass} max-w-40`}
          value={days}
          onChange={(event) => {
            setDays(event.target.value);
            setPreview(null);
          }}
        />
      </label>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Положительное число сдвигает вперёд, отрицательное — назад. Выполненные и пропущенные
        записи остаются на месте.
      </p>
      {!movable && (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          Эта запись не двигается: она выполнена, пропущена, перенесена или зафиксирована.
        </p>
      )}
      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          className={buttonClass}
          disabled={!movable || !daysValid || busy}
          onClick={() => runPreview(shiftRequest("shift_following"))}
        >
          Эта и следующие
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!movable || !daysValid || busy}
          onClick={() => runPreview(shiftRequest("shift_only"))}
        >
          Только эта
        </button>
        <button
          type="button"
          className={buttonClass}
          disabled={!canSkip || busy}
          onClick={() => runPreview({ operation: "skip", entry_id: entry.id })}
        >
          Пропустить эту
        </button>
      </div>

      {entry.kind === "workout" && (
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1 text-sm font-medium">
            Вторая тренировка
            <select
              className={inputClass}
              value={otherId}
              onChange={(event) => {
                setOtherId(event.target.value);
                setPreview(null);
              }}
            >
              <option value="">Из видимого периода</option>
              {swapCandidates.map((candidate) => (
                <option key={candidate.id} value={candidate.id}>
                  {candidate.name ?? "Тренировка"}, {formatLongDate(candidate.date)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className={buttonClass}
            disabled={!canSwap || busy}
            onClick={() =>
              runPreview({ operation: "swap", entry_id: entry.id, other_id: otherId })
            }
          >
            Поменять местами
          </button>
        </div>
      )}

      {preview && (
        <div
          role="dialog"
          aria-label="Предпросмотр сдвига"
          className="flex flex-col gap-3 rounded-lg border border-slate-200 p-3 dark:border-slate-700"
        >
          <h4 className="text-sm font-semibold">Было и станет</h4>
          <ul aria-label="Было и станет" className="flex flex-col gap-1 text-sm">
            {preview.result.changes.map((change) => (
              <li key={change.id}>{changeText(change)}</li>
            ))}
          </ul>
          {preview.result.conflicts.length > 0 && (
            <p role="alert" className="text-sm text-amber-700 dark:text-amber-300">
              {conflictText(preview.result)}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {preview.result.conflicts.length === 0 && (
              <button type="button" className={primaryButtonClass} disabled={busy} onClick={apply}>
                Применить
              </button>
            )}
            {preview.result.conflicts.length > 0 &&
              preview.result.resolutions.includes("cascade") && (
                <button
                  type="button"
                  className={buttonClass}
                  disabled={busy}
                  onClick={() => chooseResolution("cascade")}
                >
                  Сдвинуть цепочку дальше
                </button>
              )}
            {preview.result.conflicts.length > 0 && preview.result.resolutions.includes("stack") && (
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => chooseResolution("stack")}
              >
                Оставить две в один день
              </button>
            )}
            <button type="button" className={buttonClass} onClick={() => setPreview(null)}>
              Отменить
            </button>
          </div>
        </div>
      )}

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error.message}
        </p>
      )}
    </div>
  );
}
