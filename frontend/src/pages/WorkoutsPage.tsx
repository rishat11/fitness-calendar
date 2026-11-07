import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { type Workout } from "../api/client";
import {
  useCopyWorkout,
  useCreateWorkout,
  useDeleteWorkout,
  useRenameWorkout,
  useWorkouts,
} from "../features/workouts/useWorkouts";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";

function exerciseCountLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return `${count} упражнение`;
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return `${count} упражнения`;
  return `${count} упражнений`;
}

function WorkoutRow({ workout }: { workout: Workout }) {
  const rename = useRenameWorkout();
  const copy = useCopyWorkout();
  const remove = useDeleteWorkout();
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(workout.name);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const busy = rename.isPending || copy.isPending || remove.isPending;

  const handleRename = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "" || trimmed === workout.name) {
      setRenaming(false);
      return;
    }
    rename.mutate({ id: workout.id, name: trimmed }, { onSuccess: () => setRenaming(false) });
  };

  return (
    <li className="flex flex-col gap-2 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-slate-800">
      {renaming ? (
        <form onSubmit={handleRename} aria-label="Переименование тренировки" className="flex flex-1 flex-wrap gap-2">
          <input
            aria-label="Новое название"
            className={`${inputClass} flex-1`}
            value={name}
            onChange={(event) => setName(event.target.value)}
          />
          <button type="submit" className={buttonClass} disabled={busy}>
            Сохранить
          </button>
          <button
            type="button"
            className={buttonClass}
            onClick={() => {
              setName(workout.name);
              setRenaming(false);
            }}
          >
            Отмена
          </button>
          {rename.isError && (
            <span role="alert" className="w-full text-sm text-red-600">
              {rename.error.message}
            </span>
          )}
        </form>
      ) : (
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium">{workout.name}</p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {exerciseCountLabel(workout.items.length)}
          </p>
        </div>
      )}

      {!renaming && (
        <div className="flex flex-wrap items-center gap-1">
          {confirmingDelete ? (
            <>
              <span className="text-sm">Удалить тренировку?</span>
              <button
                type="button"
                className={`${buttonClass} text-red-600`}
                disabled={busy}
                onClick={() => remove.mutate(workout.id)}
              >
                Удалить
              </button>
              <button type="button" className={buttonClass} onClick={() => setConfirmingDelete(false)}>
                Отмена
              </button>
            </>
          ) : (
            <>
              <Link
                to={`/workouts/${workout.id}`}
                className={`${buttonClass} inline-flex items-center bg-slate-900 text-white hover:bg-slate-700 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300`}
              >
                Открыть
              </Link>
              <button type="button" className={buttonClass} disabled={busy} onClick={() => setRenaming(true)}>
                Переименовать
              </button>
              <button
                type="button"
                className={buttonClass}
                disabled={busy}
                onClick={() => copy.mutate(workout.id)}
              >
                Копировать
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
        </div>
      )}
    </li>
  );
}

export function WorkoutsPage() {
  const navigate = useNavigate();
  const { data: workouts, isPending, isError } = useWorkouts();
  const createWorkout = useCreateWorkout();
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleCreate = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "") {
      setError("Укажите название");
      return;
    }
    setError(null);
    createWorkout.mutate(
      { name: trimmed, items: [] },
      { onSuccess: (workout) => navigate(`/workouts/${workout.id}`, { state: { editing: true } }) },
    );
  };

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <h1 className="text-2xl font-semibold">Мои тренировки</h1>

      <form
        onSubmit={handleCreate}
        noValidate
        aria-label="Новая тренировка"
        className="flex flex-col gap-3 rounded-xl border border-slate-200 p-4 sm:flex-row sm:items-end dark:border-slate-800"
      >
        <label className="flex flex-1 flex-col gap-1 text-sm font-medium">
          Название тренировки
          <input
            className={inputClass}
            value={name}
            placeholder="Например, «Спина» или «Верх»"
            aria-invalid={error ? true : undefined}
            onChange={(event) => setName(event.target.value)}
          />
        </label>
        <div className="flex min-h-11 flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={createWorkout.isPending}
            className="min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300"
          >
            Создать
          </button>
          {error && (
            <span role="alert" className="text-sm text-red-600">
              {error}
            </span>
          )}
          {createWorkout.isError && (
            <span role="alert" className="text-sm text-red-600">
              {createWorkout.error.message}
            </span>
          )}
        </div>
      </form>

      {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
      {isError && <p className="text-red-600">Не удалось загрузить тренировки. Обновите страницу.</p>}
      {workouts && workouts.length === 0 && (
        <p className="text-slate-600 dark:text-slate-300">
          Тренировок пока нет. Создайте первую выше и добавьте в неё упражнения.
        </p>
      )}

      {workouts && workouts.length > 0 && (
        <ul className="flex flex-col gap-3" aria-label="Список тренировок">
          {workouts.map((workout) => (
            <WorkoutRow key={workout.id} workout={workout} />
          ))}
        </ul>
      )}
    </div>
  );
}
