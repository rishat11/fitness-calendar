import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  type Exercise,
  type ExerciseHistoryBest,
  type ExerciseHistorySession,
  type ExerciseHistorySet,
} from "../api/client";
import { formatLongDate } from "../features/calendar/dates";
import {
  EQUIPMENT_OPTIONS,
  MUSCLE_OPTIONS,
  labelFor,
} from "../features/exercises/options";
import { ProgressChart, type ChartPoint } from "../features/exercises/ProgressChart";
import { ProgressionHintCard } from "../features/progression/ProgressionHint";

const buttonClass =
  "inline-flex min-h-11 items-center rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 dark:text-slate-200 dark:hover:bg-slate-800";

function formatNumber(value: number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(value);
}

function unitLabel(unit: string | null | undefined): string {
  return unit === "lb" ? "lb" : "кг";
}

function formatHistorySet(set: ExerciseHistorySet): string {
  const unit = unitLabel(set.weight_unit);
  const parts = [
    set.weight == null ? "без веса" : `${formatNumber(set.weight)} ${unit}`,
  ];
  if (set.extra_weight != null) parts.push(`доп. ${formatNumber(set.extra_weight)} ${unit}`);
  parts.push(set.reps == null ? "без повторов" : `${set.reps} повт.`);
  if (set.rir != null) parts.push(`RIR ${set.rir >= 5 ? "4+" : set.rir}`);
  if (set.is_assisted) parts.push("с помощью");
  if (set.is_negative) parts.push("негативы");
  return parts.join(", ");
}

function formatBest(best: ExerciseHistoryBest): string {
  const parts: string[] = [];
  if (best.load != null) parts.push(`нагрузка ${formatNumber(best.load)} ${unitLabel(best.weight_unit)}`);
  parts.push(`${best.reps} повт.`);
  if (best.epley_1rm != null) parts.push(`расчётный 1ПМ ${formatNumber(best.epley_1rm)}`);
  return `Лучший рабочий подход: ${parts.join(", ")}`;
}

function chartPoints(sessions: ExerciseHistorySession[]): ChartPoint[] {
  return sessions
    .flatMap((session) =>
      session.best
        ? [
            {
              date: session.date,
              startedAt: session.started_at,
              load: session.best.load,
              reps: session.best.reps,
              epley_1rm: session.best.epley_1rm,
              weight_unit: session.best.weight_unit,
            },
          ]
        : [],
    )
    .sort((a, b) => a.date.localeCompare(b.date) || a.startedAt.localeCompare(b.startedAt));
}

function SessionResults({ session }: { session: ExerciseHistorySession }) {
  const working = session.sets.filter((set) => !set.is_warmup);
  const warmup = session.sets.filter((set) => set.is_warmup);
  const [open, setOpen] = useState(working.length === 0);

  return (
    <article className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 dark:border-slate-800">
      <h3 className="font-medium">{formatLongDate(session.date)}</h3>
      {session.best && (
        <p className="text-sm text-slate-600 dark:text-slate-300">{formatBest(session.best)}</p>
      )}
      {working.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm">
          {working.map((set, index) => (
            <li key={`${session.performed_id}-w-${index}`}>{formatHistorySet(set)}</li>
          ))}
        </ul>
      )}
      {warmup.length > 0 && (
        <>
          <button
            type="button"
            className={buttonClass}
            aria-expanded={open}
            onClick={() => setOpen((value) => !value)}
          >
            {open ? "Скрыть разминку" : `Разминка (${warmup.length})`}
          </button>
          {open && (
            <ul className="flex flex-col gap-1 text-sm text-slate-600 dark:text-slate-300">
              {warmup.map((set, index) => (
                <li key={`${session.performed_id}-u-${index}`}>Разминка: {formatHistorySet(set)}</li>
              ))}
            </ul>
          )}
        </>
      )}
    </article>
  );
}

function ExerciseFacts({ exercise }: { exercise: Exercise }) {
  return (
    <div className="flex flex-col gap-1 text-sm text-slate-600 dark:text-slate-300">
      <p>
        {labelFor(MUSCLE_OPTIONS, exercise.primary_muscle)} ·{" "}
        {labelFor(EQUIPMENT_OPTIONS, exercise.equipment)}
      </p>
      <p>
        Повторы {exercise.rep_min}–{exercise.rep_max} · шаг{" "}
        {formatNumber(exercise.weight_step)} {unitLabel(exercise.weight_unit)}
      </p>
    </div>
  );
}

export function ExerciseCardPage() {
  const { exerciseId = "" } = useParams();
  const exercise = useQuery({
    queryKey: ["exercise", exerciseId],
    queryFn: () => api.getExercise(exerciseId),
    enabled: exerciseId.length > 0,
  });
  const history = useQuery({
    queryKey: ["exercise-history", exerciseId],
    queryFn: () => api.exerciseHistory(exerciseId),
    enabled: exerciseId.length > 0,
  });

  const back = (
    <Link to="/exercises" className={`${buttonClass} w-fit`}>
      К упражнениям
    </Link>
  );

  if (!exerciseId) return null;
  if (exercise.isPending || history.isPending) {
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        {back}
        <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>
      </div>
    );
  }
  if (exercise.isError || history.isError || !exercise.data || !history.data) {
    const error = exercise.error ?? history.error;
    const message =
      error instanceof ApiError ? error.message : "Не удалось открыть карточку упражнения";
    return (
      <div className="flex max-w-3xl flex-col gap-4">
        {back}
        <p role="alert" className="text-red-600">
          {message}
        </p>
      </div>
    );
  }

  const sessions = history.data.sessions;
  const notes = sessions.flatMap((session) =>
    session.notes.map((note) => ({ id: `${session.performed_id}:${note}`, date: session.date, note })),
  );
  const points = chartPoints(sessions);

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      {back}
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold">{exercise.data.name}</h1>
        <ExerciseFacts exercise={exercise.data} />
      </header>

      <ProgressionHintCard exerciseId={exerciseId} />

      {sessions.length === 0 ? (
        <p className="text-slate-600 dark:text-slate-300">
          Истории пока нет. Завершите тренировку с этим упражнением — здесь появятся заметки,
          результаты и график.
        </p>
      ) : (
        <>
          <section aria-label="Заметки" className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Заметки</h2>
            {notes.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">Заметок пока нет.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {notes.map((entry) => (
                  <li
                    key={entry.id}
                    className="rounded-xl border border-slate-200 p-4 dark:border-slate-800"
                  >
                    <p className="text-sm text-slate-600 dark:text-slate-300">
                      {formatLongDate(entry.date)}
                    </p>
                    <p>{entry.note}</p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-label="Прошлые результаты" className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">Прошлые результаты</h2>
            {sessions.map((session) => (
              <SessionResults key={session.performed_id} session={session} />
            ))}
          </section>

          <section aria-label="График" className="flex flex-col gap-3">
            <h2 className="text-lg font-medium">График</h2>
            {points.length === 0 ? (
              <p className="text-sm text-slate-600 dark:text-slate-300">
                Нет завершённых рабочих подходов для графика.
              </p>
            ) : (
              <ProgressChart points={points} />
            )}
          </section>
        </>
      )}
    </div>
  );
}
