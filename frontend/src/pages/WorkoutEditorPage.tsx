import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { type Exercise, type Workout } from "../api/client";
import { QuickExerciseForm } from "../components/QuickExerciseForm";
import { useProfile } from "../features/profile/useProfile";
import { useExercises } from "../features/exercises/useExercises";
import {
  EQUIPMENT_OPTIONS,
  MUSCLE_OPTIONS,
  describeExercise,
  labelFor,
  type WeightUnit,
} from "../features/exercises/options";
import {
  MAX_SETS,
  draftFromWorkout,
  draftSignature,
  moveItem,
  newItemDraft,
  newSetDraft,
  validateDraft,
  type ItemDraft,
  type SetDraft,
  type WorkoutDraft,
} from "../features/workouts/draft";
import { useUpdateWorkout, useWorkout } from "../features/workouts/useWorkouts";

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const inputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const smallInputClass =
  "min-h-11 w-full rounded-lg border border-slate-300 bg-white px-2 text-base dark:border-slate-700 dark:bg-slate-900 sm:w-24";
const labelClass = "flex flex-col gap-1 text-sm font-medium";
const sectionClass = "flex flex-col gap-3 rounded-xl border border-slate-200 p-4 dark:border-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-5 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";

function describeSet(set: Workout["items"][number]["sets"][number]): string {
  const reps = set.rep_min === set.rep_max ? String(set.rep_min) : `${set.rep_min}–${set.rep_max}`;
  const parts = [`${reps} повт.`];
  if (set.target_rir != null) parts.push(`RIR ${set.target_rir >= 5 ? "4+" : set.target_rir}`);
  if (set.rest_seconds != null) parts.push(`отдых ${set.rest_seconds} с`);
  return parts.join(", ");
}

type SetRowProps = {
  exerciseName: string;
  number: number;
  set: SetDraft;
  canRemove: boolean;
  onChange: (patch: Partial<SetDraft>) => void;
  onRemove: () => void;
};

function SetRow({ exerciseName, number, set, canRemove, onChange, onRemove }: SetRowProps) {
  const context = `${exerciseName}, подход ${number}`;
  return (
    <li className="flex flex-wrap items-end gap-2">
      <span className="min-h-11 w-20 self-center text-sm font-medium">Подход {number}</span>
      <label className={labelClass}>
        <span className="text-xs text-slate-600 dark:text-slate-300">Повторы от</span>
        <input
          aria-label={`${context}: повторы от`}
          inputMode="numeric"
          className={smallInputClass}
          value={set.repMin}
          onChange={(event) => onChange({ repMin: event.target.value })}
        />
      </label>
      <label className={labelClass}>
        <span className="text-xs text-slate-600 dark:text-slate-300">до</span>
        <input
          aria-label={`${context}: повторы до`}
          inputMode="numeric"
          className={smallInputClass}
          value={set.repMax}
          onChange={(event) => onChange({ repMax: event.target.value })}
        />
      </label>
      <label className={labelClass}>
        <span className="text-xs text-slate-600 dark:text-slate-300">RIR</span>
        <select
          aria-label={`${context}: RIR`}
          className={smallInputClass}
          value={set.targetRir}
          onChange={(event) => onChange({ targetRir: event.target.value })}
        >
          <option value="">—</option>
          {[0, 1, 2, 3, 4, 5].map((value) => (
            <option key={value} value={value}>
              {value}
            </option>
          ))}
        </select>
      </label>
      <label className={labelClass}>
        <span className="text-xs text-slate-600 dark:text-slate-300">Отдых, с</span>
        <input
          aria-label={`${context}: отдых, секунды`}
          inputMode="numeric"
          className={smallInputClass}
          value={set.restSeconds}
          onChange={(event) => onChange({ restSeconds: event.target.value })}
        />
      </label>
      <button
        type="button"
        className={buttonClass}
        disabled={!canRemove}
        aria-label={`Убрать подход ${number}, ${exerciseName}`}
        onClick={onRemove}
      >
        Убрать
      </button>
    </li>
  );
}

type ItemCardProps = {
  item: ItemDraft;
  index: number;
  total: number;
  onMove: (delta: -1 | 1) => void;
  onRemove: () => void;
  onSetsChange: (sets: SetDraft[]) => void;
};

function ItemCard({ item, index, total, onMove, onRemove, onSetsChange }: ItemCardProps) {
  const name = item.exercise.name;
  const addSet = () => {
    const last = item.sets[item.sets.length - 1];
    onSetsChange([...item.sets, newSetDraft(last ? { ...last } : undefined)]);
  };

  return (
    <li className={sectionClass} aria-label={`Упражнение ${index + 1}: ${name}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <p className="font-medium">
            {index + 1}. {name}
          </p>
          <p className="text-sm text-slate-600 dark:text-slate-300">
            {labelFor(MUSCLE_OPTIONS, item.exercise.primary_muscle)} ·{" "}
            {labelFor(EQUIPMENT_OPTIONS, item.exercise.equipment)}
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          <button
            type="button"
            className={buttonClass}
            disabled={index === 0}
            aria-label={`Поднять ${name}`}
            onClick={() => onMove(-1)}
          >
            Выше
          </button>
          <button
            type="button"
            className={buttonClass}
            disabled={index === total - 1}
            aria-label={`Опустить ${name}`}
            onClick={() => onMove(1)}
          >
            Ниже
          </button>
          <button type="button" className={`${buttonClass} text-red-600`} onClick={onRemove}>
            Убрать упражнение
          </button>
        </div>
      </div>

      <ol className="flex flex-col gap-3">
        {item.sets.map((set, setIndex) => (
          <SetRow
            key={set.key}
            exerciseName={name}
            number={setIndex + 1}
            set={set}
            canRemove={item.sets.length > 1}
            onChange={(patch) =>
              onSetsChange(item.sets.map((current) => (current.key === set.key ? { ...current, ...patch } : current)))
            }
            onRemove={() => onSetsChange(item.sets.filter((current) => current.key !== set.key))}
          />
        ))}
      </ol>

      <div>
        <button
          type="button"
          className={buttonClass}
          disabled={item.sets.length >= MAX_SETS}
          onClick={addSet}
        >
          Добавить подход
        </button>
      </div>
    </li>
  );
}

type ExercisePickerProps = {
  weightUnit: WeightUnit;
  onPick: (exercise: Exercise) => void;
};

function ExercisePicker({ weightUnit, onPick }: ExercisePickerProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const { data: exercises, isPending, isError } = useExercises({ search });

  return (
    <section aria-label="Добавить упражнение" className="flex flex-col gap-4">
      <button
        type="button"
        className={`${buttonClass} self-start border border-slate-300 dark:border-slate-700`}
        aria-expanded={open}
        aria-controls="add-exercise-panel"
        onClick={() => setOpen((value) => !value)}
      >
        Добавить упражнение
      </button>
      {open && (
        <div id="add-exercise-panel" className="flex flex-col gap-4">
          <QuickExerciseForm weightUnit={weightUnit} onCreated={onPick} />

          <label className={labelClass}>
            Поиск в справочнике
            <input
              type="search"
              className={inputClass}
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </label>

          {isPending && <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>}
          {isError && <p className="text-red-600">Не удалось загрузить справочник.</p>}
          {exercises && exercises.length === 0 && (
            <p className="text-slate-600 dark:text-slate-300">
              {search.trim() ? "Ничего не найдено" : "В справочнике пока нет упражнений"}
            </p>
          )}
          {exercises && exercises.length > 0 && (
            <ul className="flex flex-col gap-2" aria-label="Упражнения справочника">
              {exercises.map((exercise) => (
                <li
                  key={exercise.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-slate-200 p-3 dark:border-slate-800"
                >
                  <div className="flex min-w-0 flex-col">
                    <span className="font-medium">{exercise.name}</span>
                    <span className="text-sm text-slate-600 dark:text-slate-300">
                      {describeExercise(exercise)}
                    </span>
                  </div>
                  <button type="button" className={buttonClass} onClick={() => onPick(exercise)}>
                    В тренировку
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function WorkoutView({ workout, onEdit }: { workout: Workout; onEdit: () => void }) {
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{workout.name}</h1>
        <button type="button" className={primaryButtonClass} onClick={onEdit}>
          Редактировать
        </button>
      </div>

      <section aria-label="Упражнения тренировки" className="flex flex-col gap-4">
        <h2 className="text-lg font-semibold">Упражнения</h2>
        {workout.items.length === 0 && (
          <p className="text-slate-600 dark:text-slate-300">В тренировке пока нет упражнений.</p>
        )}
        <ol className="flex flex-col gap-4">
          {workout.items.map((item, index) => (
            <li
              key={item.id}
              className={sectionClass}
              aria-label={`Упражнение ${index + 1}: ${item.exercise.name}`}
            >
              <div className="flex min-w-0 flex-col gap-1">
                <p className="font-medium">
                  {index + 1}. {item.exercise.name}
                </p>
                <p className="text-sm text-slate-600 dark:text-slate-300">
                  {labelFor(MUSCLE_OPTIONS, item.exercise.primary_muscle)} ·{" "}
                  {labelFor(EQUIPMENT_OPTIONS, item.exercise.equipment)}
                </p>
              </div>
              <ol className="flex flex-col gap-2">
                {item.sets.map((set, setIndex) => (
                  <li key={set.id} className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                    <span className="text-sm font-medium">Подход {setIndex + 1}</span>
                    <span className="text-sm text-slate-600 dark:text-slate-300">{describeSet(set)}</span>
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ol>
      </section>
    </>
  );
}

function WorkoutEditor({ workout, initialEditing }: { workout: Workout; initialEditing: boolean }) {
  const { data: profile } = useProfile();
  const weightUnit = profile?.weight_unit ?? "kg";
  const [editing, setEditing] = useState(initialEditing);
  // Черновик живёт только в режиме правки и не сбрасывается ответом сервера, пока правка открыта.
  const [draft, setDraft] = useState<WorkoutDraft>(() => draftFromWorkout(workout));
  // Состояние, которое сейчас на сервере (или загружено с него): по нему видно, есть ли несохранённые правки.
  const [savedSignature, setSavedSignature] = useState(() => draftSignature(draftFromWorkout(workout)));
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);
  // Ответ сохранения, пока запрос карточки ещё не обновился.
  const [preview, setPreview] = useState<Workout | null>(null);
  const update = useUpdateWorkout();
  const dirty = draftSignature(draft) !== savedSignature;
  const shown = preview ?? workout;

  useEffect(() => {
    setPreview(null);
  }, [workout]);

  // Закрытие вкладки или обновление страницы: браузер покажет своё предупреждение.
  useEffect(() => {
    if (!editing || !dirty) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [editing, dirty]);

  const confirmLeave = (event: { preventDefault: () => void }) => {
    if (editing && dirty && !window.confirm("Есть несохранённые изменения. Выйти без сохранения?")) {
      event.preventDefault();
    }
  };

  const startEditing = () => {
    const next = draftFromWorkout(shown);
    setDraft(next);
    setSavedSignature(draftSignature(next));
    setErrors([]);
    setSaved(false);
    setEditing(true);
  };

  const cancelEditing = () => {
    if (dirty && !window.confirm("Есть несохранённые изменения. Выйти без сохранения?")) return;
    setErrors([]);
    setSaved(false);
    update.reset();
    setEditing(false);
  };

  const edit = (change: (current: WorkoutDraft) => WorkoutDraft) => {
    setDraft(change);
    setSaved(false);
    setErrors([]);
    update.reset();
  };

  const setItems = (change: (items: ItemDraft[]) => ItemDraft[]) =>
    edit((current) => ({ ...current, items: change(current.items) }));

  const handleSave = () => {
    const { errors: problems, input } = validateDraft(draft);
    setErrors(problems);
    if (!input) return;
    const sentSignature = draftSignature(draft);
    update.mutate(
      { id: workout.id, body: input },
      {
        onSuccess: (savedWorkout) => {
          setPreview(savedWorkout);
          setSavedSignature(sentSignature);
          setSaved(true);
          setEditing(false);
        },
      },
    );
  };

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <Link
        to="/workouts"
        onClick={confirmLeave}
        className="self-start text-sm text-slate-600 underline dark:text-slate-300"
      >
        ← Все тренировки
      </Link>

      {editing ? (
        <>
          <label className={labelClass}>
            <span className="text-2xl font-semibold">Название тренировки</span>
            <input
              className={inputClass}
              value={draft.name}
              onChange={(event) => edit((current) => ({ ...current, name: event.target.value }))}
            />
          </label>

          <section aria-label="Упражнения тренировки" className="flex flex-col gap-4">
            <h2 className="text-lg font-semibold">Упражнения</h2>
            {draft.items.length === 0 && (
              <p className="text-slate-600 dark:text-slate-300">
                В тренировке пока нет упражнений. Добавьте их ниже.
              </p>
            )}
            <ol className="flex flex-col gap-4">
              {draft.items.map((item, index) => (
                <ItemCard
                  key={item.key}
                  item={item}
                  index={index}
                  total={draft.items.length}
                  onMove={(delta) => setItems((items) => moveItem(items, index, delta))}
                  onRemove={() => setItems((items) => items.filter((current) => current.key !== item.key))}
                  onSetsChange={(sets) =>
                    setItems((items) =>
                      items.map((current) => (current.key === item.key ? { ...current, sets } : current)),
                    )
                  }
                />
              ))}
            </ol>
          </section>

          <div className={sectionClass}>
            <ExercisePicker
              weightUnit={weightUnit}
              onPick={(exercise) => setItems((items) => [...items, newItemDraft(exercise)])}
            />
          </div>

          {/* На телефоне панель прилипает над нижней навигацией (высота ~4rem), выше неё по z-index. */}
          <div className="sticky bottom-16 z-20 flex flex-wrap items-center gap-3 bg-white py-3 md:bottom-0 dark:bg-slate-950">
            <button type="button" onClick={handleSave} disabled={update.isPending} className={primaryButtonClass}>
              {update.isPending ? "Сохраняем…" : "Сохранить"}
            </button>
            <button type="button" className={buttonClass} disabled={update.isPending} onClick={cancelEditing}>
              Отмена
            </button>
            {dirty && !saved && (
              <span className="text-sm text-amber-600 dark:text-amber-400">Есть несохранённые изменения</span>
            )}
            {errors.length > 0 && (
              <ul role="alert" className="flex flex-col gap-1 text-sm text-red-600">
                {errors.map((problem) => (
                  <li key={problem}>{problem}</li>
                ))}
              </ul>
            )}
            {update.isError && (
              <span role="alert" className="text-sm text-red-600">
                {update.error.message}
              </span>
            )}
          </div>
        </>
      ) : (
        <>
          <WorkoutView workout={shown} onEdit={startEditing} />
          {saved && (
            <span role="status" className="text-sm text-slate-600 dark:text-slate-300">
              Сохранено
            </span>
          )}
        </>
      )}
    </div>
  );
}

export function WorkoutEditorPage() {
  const { workoutId = "" } = useParams();
  const location = useLocation();
  const initialEditing = Boolean((location.state as { editing?: boolean } | null)?.editing);
  const { data: workout, isPending, isError } = useWorkout(workoutId);

  if (isPending) return <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>;
  if (isError || !workout) {
    return (
      <div className="flex flex-col gap-3">
        <p role="alert" className="text-red-600">
          Тренировка не найдена.
        </p>
        <Link to="/workouts" className="text-sm underline">
          Все тренировки
        </Link>
      </div>
    );
  }
  return <WorkoutEditor key={workout.id} workout={workout} initialEditing={initialEditing} />;
}
