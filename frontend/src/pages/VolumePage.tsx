import { useState } from "react";
import { Link } from "react-router-dom";
import type { MuscleVolumeGroup } from "../api/client";
import {
  addDays,
  formatWeekTitle,
  mondayOf,
  todayIso,
  weekDates,
} from "../features/calendar/dates";
import {
  barScale,
  groupTitle,
  percentOf,
  setsWord,
  statusBarClass,
  statusText,
  TARGET_MAX,
  TARGET_MIN,
} from "../features/volume/format";
import { useMuscleVolume } from "../features/volume/useVolume";

const navButton =
  "flex min-h-11 min-w-11 items-center justify-center rounded-lg border border-slate-300 px-3 text-base font-medium hover:bg-slate-200 dark:border-slate-700 dark:hover:bg-slate-800";

function VolumeRow({ group, scale }: { group: MuscleVolumeGroup; scale: number }) {
  const title = groupTitle(group);
  const status = group.status;

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h3 className="font-medium">{title}</h3>
        <p className="text-sm text-slate-700 dark:text-slate-200">
          <span className="text-base font-semibold">{group.sets}</span> {setsWord(group.sets)}
          {status && <span> · {statusText(status)}</span>}
        </p>
      </div>

      {status && (
        <>
          <div className="relative h-3 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" aria-hidden="true">
            <div
              className="absolute inset-y-0 bg-emerald-200 dark:bg-emerald-900"
              style={{
                left: `${percentOf(TARGET_MIN, scale)}%`,
                width: `${percentOf(TARGET_MAX - TARGET_MIN, scale)}%`,
              }}
            />
            <div
              className={`absolute inset-y-0 left-0 rounded-full ${statusBarClass(status)}`}
              style={{ width: `${percentOf(group.sets, scale)}%` }}
            />
          </div>
          <p className="text-xs text-slate-600 dark:text-slate-300">
            Ориентир {TARGET_MIN}–{TARGET_MAX} подходов за неделю
          </p>
        </>
      )}
    </li>
  );
}

export function VolumePage() {
  const today = todayIso();
  const [anchor, setAnchor] = useState(today);
  const days = weekDates(anchor);
  const weekStart = mondayOf(anchor);
  const isCurrentWeek = weekStart === mondayOf(today);
  const { data, isPending, isError } = useMuscleVolume(weekStart);
  const scale = data ? barScale(data.groups) : TARGET_MAX;

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">Объём по мышечным группам</h1>
        <p className="text-slate-600 dark:text-slate-300">
          Рабочие подходы за неделю. Разминка не считается, вторичные группы не добавляются к
          основной.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          aria-label="Предыдущая неделя"
          className={navButton}
          onClick={() => setAnchor(addDays(anchor, -7))}
        >
          ←
        </button>
        <h2 className="min-w-0 flex-1 text-center text-base font-semibold" aria-live="polite">
          {formatWeekTitle(days)}
        </h2>
        <button
          type="button"
          aria-label="Следующая неделя"
          className={navButton}
          onClick={() => setAnchor(addDays(anchor, 7))}
        >
          →
        </button>
        {!isCurrentWeek && (
          <button
            type="button"
            className="min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800"
            onClick={() => setAnchor(today)}
          >
            К текущей неделе
          </button>
        )}
      </div>

      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
      {isError && (
        <p role="alert" className="text-red-600">
          Не удалось загрузить объём. Обновите страницу.
        </p>
      )}

      {data && data.groups.length === 0 && (
        <div className="flex flex-col items-start gap-2 rounded-xl border border-dashed border-slate-300 p-4 dark:border-slate-700">
          <p className="font-medium">За эту неделю рабочих подходов нет</p>
          <p className="text-slate-600 dark:text-slate-300">
            Записанные в журнале подходы появятся здесь по группам. Можно открыть календарь и
            выбрать тренировку.
          </p>
          <Link to="/calendar" className="min-h-11 py-3 text-sm font-medium text-emerald-700 underline dark:text-emerald-400">
            Открыть календарь
          </Link>
        </div>
      )}

      {data && data.groups.length > 0 && (
        <ul aria-label="Группы за неделю" className="flex flex-col gap-3">
          {data.groups.map((group) => (
            <VolumeRow key={group.muscle ?? "none"} group={group} scale={scale} />
          ))}
        </ul>
      )}
    </div>
  );
}
