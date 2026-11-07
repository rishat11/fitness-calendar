import { Link } from "react-router-dom";
import type { PerformedWorkout } from "../../api/client";
import { formatLongDate } from "../calendar/dates";
import { setsWord } from "../volume/format";
import { buildExerciseReports, formatDuration, reportTotals } from "./report";
import { formatRecord, formatVolume, type PersonalRecord } from "./summary";

const quietButton =
  "inline-flex min-h-11 items-center rounded-xl px-3 text-sm font-medium text-stone-700 transition hover:bg-stone-200/70 dark:text-stone-200 dark:hover:bg-white/10";

function kindLabel(kind: PersonalRecord["kind"]): string {
  if (kind === "weight") return "Вес";
  if (kind === "reps") return "Повторы";
  return "1ПМ";
}

export function WorkoutReport({
  workout,
  onClose,
}: {
  workout: PerformedWorkout;
  onClose: () => void;
}) {
  const totals = reportTotals(workout);
  const duration = formatDuration(workout.started_at, workout.finished_at);
  const records = workout.summary.records ?? [];
  const exercises = buildExerciseReports(workout.items);
  const when = [formatLongDate(workout.date), duration].filter(Boolean).join(" · ");

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <button type="button" className={quietButton} onClick={onClose}>
          К записи
        </button>
        <Link to="/calendar" className={quietButton}>
          К календарю
        </Link>
      </div>

      <article className="card overflow-hidden">
        <header className="bg-gradient-to-br from-emerald-700 to-emerald-900 px-5 py-6 text-white">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-100">Отчёт</p>
          <h1 className="mt-1 text-2xl font-bold tracking-tight">{workout.name ?? "Тренировка"}</h1>
          <p className="mt-1 text-sm text-emerald-50">{when}</p>
        </header>
        <dl className="grid grid-cols-3 divide-x divide-stone-200 dark:divide-white/10">
          <div className="flex flex-col gap-1 px-3 py-4 text-center">
            <dt className="text-xs text-stone-600 dark:text-stone-300">Подходы</dt>
            <dd className="text-xl font-bold tabular-nums">{totals.workingSets}</dd>
            <dd className="text-xs text-stone-600 dark:text-stone-300">{setsWord(totals.workingSets)}</dd>
          </div>
          <div className="flex flex-col gap-1 px-3 py-4 text-center">
            <dt className="text-xs text-stone-600 dark:text-stone-300">Объём</dt>
            <dd className="text-xl font-bold tabular-nums">{formatVolume(totals.volume, totals.unit)}</dd>
          </div>
          <div className="flex flex-col gap-1 px-3 py-4 text-center">
            <dt className="text-xs text-stone-600 dark:text-stone-300">Рекорды</dt>
            <dd className="text-xl font-bold tabular-nums">{records.length}</dd>
          </div>
        </dl>
      </article>

      <section className="flex flex-col gap-3" aria-label="Личные рекорды">
        <h2 className="text-lg font-semibold">Личные рекорды</h2>
        {records.length === 0 ? (
          <p className="text-sm text-stone-600 dark:text-stone-300">В этой тренировке рекордов нет.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {records.map((record) => (
              <li key={`${record.exercise_id}-${record.kind}`} className="card flex flex-col gap-1 p-4">
                <p className="text-xs font-semibold uppercase tracking-wider text-emerald-700 dark:text-emerald-400">
                  {kindLabel(record.kind)}
                </p>
                <p className="font-medium">{formatRecord(record)}</p>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="text-lg font-semibold">Упражнения</h2>
        {exercises.length === 0 ? (
          <p className="text-sm text-stone-600 dark:text-stone-300">Упражнений нет.</p>
        ) : (
          <ol className="flex flex-col gap-3">
            {exercises.map((exercise, index) => (
              <li key={exercise.id} className="card flex flex-col gap-3 p-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <h3 className="font-semibold">
                    {index + 1}. {exercise.name}
                  </h3>
                  <p className="text-sm text-stone-600 dark:text-stone-300">
                    {exercise.workingSets} {setsWord(exercise.workingSets)}
                    {exercise.volume > 0 && ` · ${formatVolume(exercise.volume, exercise.unit)}`}
                  </p>
                </div>
                {exercise.lines.length === 0 ? (
                  <p className="text-sm text-stone-600 dark:text-stone-300">Подходы не записаны.</p>
                ) : (
                  <ul className="flex flex-col gap-2">
                    {exercise.lines.map((line) => (
                      <li key={line.id} className="text-sm">
                        <p className={line.warmup ? "text-stone-600 dark:text-stone-300" : "font-medium"}>{line.text}</p>
                        {line.note && <p className="text-stone-600 dark:text-stone-300">{line.note}</p>}
                      </li>
                    ))}
                  </ul>
                )}
                {exercise.note && <p className="text-sm text-stone-600 dark:text-stone-300">{exercise.note}</p>}
              </li>
            ))}
          </ol>
        )}
      </section>

      {workout.note && (
        <section className="card flex flex-col gap-1 p-4">
          <h2 className="text-sm font-semibold">Заметка</h2>
          <p className="whitespace-pre-wrap text-sm text-stone-700 dark:text-stone-200">{workout.note}</p>
        </section>
      )}
    </div>
  );
}
