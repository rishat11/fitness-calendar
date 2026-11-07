import { useState } from "react";
import { Link } from "react-router-dom";
import { type Exercise } from "../api/client";
import { ExerciseForm } from "../components/ExerciseForm";
import { QuickExerciseForm } from "../components/QuickExerciseForm";
import { useProfile } from "../features/profile/useProfile";
import { useDeleteExercise, useExercises } from "../features/exercises/useExercises";
import {
  WEIGHT_TYPE_OPTIONS,
  describeExercise,
  labelFor,
} from "../features/exercises/options";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";

type Mode = { type: "idle" } | { type: "create" } | { type: "edit"; id: string };

function ExerciseRow({ exercise, onEdit }: { exercise: Exercise; onEdit: () => void }) {
  const remove = useDeleteExercise();
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const busy = remove.isPending;

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
      <div className="flex min-w-0 flex-col gap-1">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            to={`/exercises/${exercise.id}`}
            className="inline-flex min-h-11 items-center font-medium hover:underline"
          >
            {exercise.name}
          </Link>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-300">{describeExercise(exercise)}</p>
        <p className="text-sm text-slate-600 dark:text-slate-300">
          {labelFor(WEIGHT_TYPE_OPTIONS, exercise.weight_type)} · повторы {exercise.rep_min}–
          {exercise.rep_max} · шаг {exercise.weight_step} {exercise.weight_unit}
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-1">
        {confirmingDelete ? (
          <>
            <span className="text-sm">Удалить навсегда?</span>
            <button
              type="button"
              className={`${buttonClass} text-red-600`}
              disabled={busy}
              onClick={() => remove.mutate(exercise.id)}
            >
              Удалить
            </button>
            <button type="button" className={buttonClass} onClick={() => setConfirmingDelete(false)}>
              Отмена
            </button>
          </>
        ) : (
          <>
            <button type="button" className={buttonClass} disabled={busy} onClick={onEdit}>
              Изменить
            </button>
            <button
              type="button"
              className={buttonClass}
              disabled={busy}
              onClick={() => setConfirmingDelete(true)}
            >
              Удалить
            </button>
          </>
        )}
        {remove.isError && (
          <span role="alert" className="w-full text-sm text-red-600">
            {remove.error.message}
          </span>
        )}
      </div>
    </li>
  );
}

export function ExercisesPage() {
  const { data: profile } = useProfile();
  const weightUnit = profile?.weight_unit ?? "kg";
  const [search, setSearch] = useState("");
  const [mode, setMode] = useState<Mode>({ type: "idle" });
  const { data: exercises, isPending, isError } = useExercises({ search });

  const closeForm = () => setMode({ type: "idle" });

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">Упражнения</h1>

      <QuickExerciseForm weightUnit={weightUnit} />

      {mode.type === "create" ? null : (
        <button
          type="button"
          onClick={() => setMode({ type: "create" })}
          className="min-h-11 self-start rounded-lg border border-slate-300 px-4 text-sm font-medium hover:bg-slate-200 dark:border-slate-700 dark:hover:bg-slate-800"
        >
          Создать подробно
        </button>
      )}

      {mode.type === "create" && (
        <ExerciseForm defaultWeightUnit={weightUnit} onDone={closeForm} />
      )}

      <label className="flex flex-col gap-1 text-sm font-medium">
        Поиск по названию
        <input
          type="search"
          className="min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>

      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
      {isError && <p className="text-red-600">Не удалось загрузить упражнения. Обновите страницу.</p>}
      {exercises && exercises.length === 0 && (
        <p className="text-slate-600 dark:text-slate-300">
          {search.trim() ? "Ничего не найдено" : "Упражнений пока нет. Добавьте первое выше."}
        </p>
      )}

      {exercises && exercises.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Список упражнений">
          {exercises.map((exercise) =>
            mode.type === "edit" && mode.id === exercise.id ? (
              <li key={exercise.id}>
                <ExerciseForm exercise={exercise} onDone={closeForm} />
              </li>
            ) : (
              <ExerciseRow
                key={exercise.id}
                exercise={exercise}
                onEdit={() => setMode({ type: "edit", id: exercise.id })}
              />
            ),
          )}
        </ul>
      )}
    </div>
  );
}