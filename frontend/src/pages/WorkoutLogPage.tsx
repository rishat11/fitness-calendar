import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  ApiError,
  api,
  sendJson,
  type PerformedItem,
  type PerformedWorkout,
  type SetLog,
} from "../api/client";
import { formatLongDate } from "../features/calendar/dates";
import { useExercises } from "../features/exercises/useExercises";
import {
  copiedLoad,
  decimalDraft,
  formatWeightInput,
  parseDecimal,
  parseWhole,
  rirLabel,
  setWrite,
  stepNumber,
  targetLabel,
  weightFields,
} from "../features/log/fields";
import {
  cancelPendingDelete,
  enqueue,
  flushOutbox,
  isRetryable,
  queueSetDelete,
  readOutbox,
  type OutboxOp,
} from "../features/log/outbox";
import { WorkoutReport } from "../features/log/WorkoutReport";
import { formatVolume, moveFocus, summarize } from "../features/log/summary";
import { RestTimerPanel, type RestTimerHandle } from "../features/log/RestTimerPanel";
import { useWakeLock } from "../features/log/useWakeLock";
import { ProgressionHintCard } from "../features/progression/ProgressionHint";

const SAVE_DELAY_MS = 300;
const RIR_VALUES = [0, 1, 2, 3, 4, 5];

const buttonClass =
  "min-h-11 rounded-lg px-3 text-sm font-medium text-slate-700 hover:bg-slate-200 disabled:opacity-50 dark:text-slate-200 dark:hover:bg-slate-800";
const primaryButtonClass =
  "min-h-11 rounded-lg bg-slate-900 px-4 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-slate-300";
const inputClass =
  "min-h-11 rounded-lg border border-slate-300 bg-white px-3 text-base dark:border-slate-700 dark:bg-slate-900";
const stepButtonClass =
  "flex size-11 shrink-0 items-center justify-center rounded-lg border border-slate-300 text-lg hover:bg-slate-200 dark:border-slate-700 dark:hover:bg-slate-800";

type SaveState = "saved" | "saving" | "pending" | "error";

const SAVE_LABEL: Record<SaveState, string> = {
  saved: "Сохранено",
  saving: "Сохраняем…",
  pending: "Нет связи — данные на этом устройстве, отправим при восстановлении",
  error: "Не удалось сохранить",
};

function isPerformed(value: unknown): value is PerformedWorkout {
  return typeof value === "object" && value !== null && "finished_at" in value && "summary" in value;
}

function withSets(item: PerformedItem, sets: SetLog[]): PerformedItem {
  return { ...item, sets: sets.map((logged, index) => ({ ...logged, position: index })) };
}

export function WorkoutLogPage() {
  const { plannedId } = useParams();
  const query = useQuery({
    queryKey: ["performed", "by-plan", plannedId],
    queryFn: () => api.startPerformed(plannedId ?? ""),
    enabled: Boolean(plannedId),
    staleTime: Infinity,
    retry: false,
  });

  if (!plannedId) return null;
  if (query.isPending) return <p className="text-slate-600 dark:text-slate-300">Загрузка…</p>;
  if (query.isError) {
    const message = query.error instanceof ApiError ? query.error.message : "Не удалось открыть тренировку";
    return (
      <p role="alert" className="text-red-600">
        {message}
      </p>
    );
  }
  return <LogEditor key={query.data.id} initial={query.data} />;
}

function LogEditor({ initial }: { initial: PerformedWorkout }) {
  const queryClient = useQueryClient();
  const [workout, setWorkout] = useState(initial);
  const workoutRef = useRef(initial);
  const [saveState, setSaveState] = useState<SaveState>("saved");
  const [error, setError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);
  const [undo, setUndo] = useState<{ itemId: string; set: SetLog } | null>(null);
  const [reportOpen, setReportOpen] = useState(false);
  const timer = useRef<number | null>(null);
  const { data: exercises = [] } = useExercises({ search: "" });
  useWakeLock(true);
  const restRef = useRef<RestTimerHandle>(null);
  // Подходы, по которым таймер уже отработал. Уже сохранённые с сервера не запускают его при открытии.
  const [timedSets] = useState(
    () =>
      new Set(
        initial.items
          .flatMap((item) => item.sets)
          .filter((logged) => logged.reps != null && !logged.is_warmup)
          .map((logged) => logged.id),
      ),
  );

  /** Таймер стартует после подтверждённого сервером сохранения рабочего подхода с повторами. */
  const startRestAfterSave = (setId: string) => {
    if (timedSets.has(setId)) return;
    const owner = workoutRef.current.items.find((item) => item.sets.some((logged) => logged.id === setId));
    if (!owner) return;
    const index = owner.sets.findIndex((logged) => logged.id === setId);
    const logged = owner.sets[index];
    if (logged.is_warmup || logged.reps == null) return;
    timedSets.add(setId);
    restRef.current?.autoStart(owner.targets[index]?.rest_seconds ?? null);
  };

  const flushRef = useRef<() => Promise<void>>(async () => {});

  const commit = (next: PerformedWorkout) => {
    workoutRef.current = next;
    setWorkout(next);
  };

  const schedule = () => {
    if (timer.current != null) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void flushRef.current();
    }, SAVE_DELAY_MS);
  };

  const remember = (op: OutboxOp) => {
    enqueue(op);
    setSaveState("saving");
    schedule();
  };

  useEffect(() => {
    flushRef.current = async () => {
      if (readOutbox().length === 0) {
        setSaveState((state) => (state === "error" ? state : "saved"));
        return;
      }
      setSaveState((state) => (state === "error" ? state : "saving"));
      try {
        await flushOutbox(async (op) => {
          const data = await sendJson(op.path, op.method, op.body);
          if (op.dedupeKey === "finish" && isPerformed(data)) {
            const current = workoutRef.current;
            const next = { ...current, finished_at: data.finished_at, summary: data.summary };
            commit(next);
            setReportOpen(true);
            void queryClient.invalidateQueries({ queryKey: ["plan"] });
          }
          const savedSet = /^(?:set|add):(.+)$/.exec(op.dedupeKey);
          if (savedSet) startRestAfterSave(savedSet[1]);
        });
        setError(null);
        setSaveState(readOutbox().length === 0 ? "saved" : "pending");
      } catch (err) {
        if (isRetryable(err)) {
          setSaveState("pending");
          setError(null);
          return;
        }
        setSaveState("error");
        setError(err instanceof Error ? err.message : "Не удалось сохранить");
      }
    };
  });

  useEffect(() => {
    void flushRef.current();
    const retry = () => {
      void flushRef.current();
    };
    window.addEventListener("online", retry);
    document.addEventListener("visibilitychange", retry);
    return () => {
      window.removeEventListener("online", retry);
      document.removeEventListener("visibilitychange", retry);
      if (timer.current != null) window.clearTimeout(timer.current);
      void flushRef.current();
    };
  }, []);

  const updateItem = (itemId: string, patch: (item: PerformedItem) => PerformedItem) => {
    const next = {
      ...workoutRef.current,
      items: workoutRef.current.items.map((item) => (item.id === itemId ? patch(item) : item)),
    };
    commit(next);
    return next;
  };

  const updateSet = (itemId: string, setId: string, patch: Partial<SetLog>) => {
    const next = updateItem(itemId, (item) =>
      withSets(
        item,
        item.sets.map((logged) => (logged.id === setId ? { ...logged, ...patch } : logged)),
      ),
    );
    const updated = next.items.flatMap((item) => item.sets).find((logged) => logged.id === setId);
    if (!updated) return;
    remember({
      dedupeKey: `set:${setId}`,
      method: "PUT",
      path: `/api/performed/${next.id}/sets/${setId}`,
      body: setWrite(updated),
    });
  };

  const addSet = (item: PerformedItem) => {
    const id = crypto.randomUUID();
    const created: SetLog = {
      id,
      position: item.sets.length,
      exercise_id: item.exercise_id,
      weight: null,
      extra_weight: null,
      reps: null,
      rir: null,
      is_warmup: false,
      is_assisted: false,
      is_negative: false,
      note: null,
    };
    const next = updateItem(item.id, (current) => withSets(current, [...current.sets, created]));
    const stored = next.items.find((current) => current.id === item.id)?.sets.find((logged) => logged.id === id);
    if (!stored) return;
    remember({
      dedupeKey: `add:${id}`,
      method: "POST",
      path: `/api/performed/${next.id}/items/${item.id}/sets`,
      body: { id, position: stored.position, ...setWrite(stored) },
    });
  };

  const removeSet = (item: PerformedItem, logged: SetLog) => {
    updateItem(item.id, (current) => withSets(current, current.sets.filter((candidate) => candidate.id !== logged.id)));
    queueSetDelete(logged.id, `/api/performed/${workoutRef.current.id}/sets/${logged.id}`);
    setPendingDelete(null);
    setUndo({ itemId: item.id, set: logged });
    setSaveState("saving");
    schedule();
  };

  const undoDelete = () => {
    if (!undo) return;
    const { itemId, set } = undo;
    const next = updateItem(itemId, (item) => {
      const rest = item.sets.filter((logged) => logged.id !== set.id);
      const index = Math.min(set.position, rest.length);
      return withSets(item, [...rest.slice(0, index), set, ...rest.slice(index)]);
    });
    const outcome = cancelPendingDelete(set.id);
    if (outcome !== "cancelled") {
      remember({
        dedupeKey: `add:${set.id}`,
        method: "POST",
        path: `/api/performed/${next.id}/items/${itemId}/sets`,
        body: { id: set.id, position: set.position, ...setWrite(set) },
      });
    } else {
      schedule();
    }
    setUndo(null);
  };

  const addExercise = (exerciseId: string) => {
    const exercise = exercises.find((candidate) => candidate.id === exerciseId);
    if (!exercise) return;
    const itemId = crypto.randomUUID();
    const setId = crypto.randomUUID();
    const item: PerformedItem = {
      id: itemId,
      position: workoutRef.current.items.length,
      exercise_id: exercise.id,
      name: exercise.name,
      equipment: exercise.equipment,
      weight_type: exercise.weight_type,
      weight_unit: exercise.weight_unit,
      weight_step: exercise.weight_step,
      note: null,
      targets: [],
      sets: [
        {
          id: setId,
          position: 0,
          exercise_id: exercise.id,
          weight: null,
          extra_weight: null,
          reps: null,
          rir: null,
          is_warmup: false,
          is_assisted: false,
          is_negative: false,
          note: null,
        },
      ],
    };
    commit({ ...workoutRef.current, items: [...workoutRef.current.items, item] });
    remember({
      dedupeKey: `add-item:${itemId}`,
      method: "POST",
      path: `/api/performed/${workoutRef.current.id}/items`,
      body: { id: itemId, set_id: setId, exercise_id: exercise.id },
    });
  };

  const replaceExercise = (item: PerformedItem, exerciseId: string) => {
    const exercise = exercises.find((candidate) => candidate.id === exerciseId);
    if (!exercise || exercise.id === item.exercise_id) return;
    updateItem(item.id, (current) => ({
      ...current,
      exercise_id: exercise.id,
      name: exercise.name,
      equipment: exercise.equipment,
      weight_type: exercise.weight_type,
      weight_unit: exercise.weight_unit,
      weight_step: exercise.weight_step,
      targets: [],
      sets: current.sets.map((logged) => ({ ...logged, exercise_id: exercise.id })),
    }));
    remember({
      dedupeKey: `exercise:${item.id}`,
      method: "PUT",
      path: `/api/performed/${workoutRef.current.id}/items/${item.id}/exercise`,
      body: { exercise_id: exercise.id },
    });
  };

  const totals = summarize(workout);

  if (reportOpen && workout.finished_at) {
    return <WorkoutReport workout={workout} onClose={() => setReportOpen(false)} />;
  }

  return (
    <div className="mx-auto flex w-full max-w-xl flex-col gap-4">
      <Link to="/calendar" className={`${buttonClass} inline-flex w-fit items-center`}>
        К календарю
      </Link>
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold">{workout.name ?? "Тренировка"}</h1>
        <p className="text-sm text-slate-600 dark:text-slate-300">{formatLongDate(workout.date)}</p>
        <p role="status" className="text-sm">
          {SAVE_LABEL[saveState]}
        </p>
        <p className="text-sm">
          Рабочих подходов: {totals.workingSets}. Объём: {formatVolume(totals.volume, totals.unit)}
        </p>
        {workout.finished_at && (
          <button type="button" className={`${primaryButtonClass} mt-2 w-fit`} onClick={() => setReportOpen(true)}>
            Отчёт
          </button>
        )}
      </header>

      {!workout.finished_at && <RestTimerPanel ref={restRef} />}

      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}

      {workout.items.length === 0 && (
        <p className="text-sm text-slate-600 dark:text-slate-300">
          В плане нет упражнений. Добавьте первое из справочника.
        </p>
      )}

      <div className="flex flex-col gap-4">
        {workout.items.map((item, itemIndex) => (
          <ExerciseBlock
            key={item.id}
            item={item}
            index={itemIndex}
            performedId={workout.id}
            exercises={exercises}
            pendingDelete={pendingDelete}
            onAskDelete={setPendingDelete}
            onCancelDelete={() => setPendingDelete(null)}
            onDelete={(logged) => removeSet(item, logged)}
            onChangeSet={(setId, patch) => updateSet(item.id, setId, patch)}
            onAddSet={() => addSet(item)}
            onReplace={(exerciseId) => replaceExercise(item, exerciseId)}
            onAppliedWeight={(setId, weight) => {
              const owner = workoutRef.current.items.find((current) =>
                current.sets.some((logged) => logged.id === setId),
              );
              if (owner) updateSet(owner.id, setId, { weight });
            }}
            onNote={(note) => {
              updateItem(item.id, (current) => ({ ...current, note }));
              remember({
                dedupeKey: `note:${item.id}`,
                method: "PATCH",
                path: `/api/performed/${workout.id}/items/${item.id}`,
                body: { note },
              });
            }}
          />
        ))}
      </div>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Добавить упражнение
        <select
          aria-label="Добавить упражнение"
          className={inputClass}
          value=""
          onChange={(event) => {
            if (event.target.value) addExercise(event.target.value);
          }}
        >
          <option value="">Выберите упражнение</option>
          {exercises.map((exercise) => (
            <option key={exercise.id} value={exercise.id}>
              {exercise.name}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-sm font-medium">
        Заметка к тренировке
        <textarea
          aria-label="Заметка к тренировке"
          className={`${inputClass} min-h-24 py-2`}
          value={workout.note ?? ""}
          maxLength={2000}
          onChange={(event) => {
            const note = event.target.value;
            commit({ ...workoutRef.current, note });
            remember({
              dedupeKey: "note:workout",
              method: "PATCH",
              path: `/api/performed/${workout.id}`,
              body: { note },
            });
          }}
        />
      </label>

      <button
        type="button"
        className={primaryButtonClass}
        onClick={() => {
          restRef.current?.reset();
          remember({
            dedupeKey: "finish",
            method: "POST",
            path: `/api/performed/${workout.id}/finish`,
            body: null,
          });
        }}
      >
        Завершить
      </button>

      {undo && (
        <div
          role="status"
          aria-label="Подход удалён"
          className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 px-3 py-2 text-sm dark:border-slate-700"
        >
          Подход удалён.
          <button type="button" className={buttonClass} onClick={undoDelete}>
            Отменить
          </button>
        </div>
      )}
    </div>
  );
}

function ExerciseBlock({
  item,
  index,
  performedId,
  exercises,
  pendingDelete,
  onAskDelete,
  onCancelDelete,
  onDelete,
  onChangeSet,
  onAddSet,
  onReplace,
  onAppliedWeight,
  onNote,
}: {
  item: PerformedItem;
  index: number;
  performedId: string;
  exercises: { id: string; name: string }[];
  pendingDelete: string | null;
  onAskDelete: (setId: string) => void;
  onCancelDelete: () => void;
  onDelete: (logged: SetLog) => void;
  onChangeSet: (setId: string, patch: Partial<SetLog>) => void;
  onAddSet: () => void;
  onReplace: (exerciseId: string) => void;
  onAppliedWeight: (setId: string, weight: number) => void;
  onNote: (note: string) => void;
}) {
  const previous = useQuery({
    queryKey: ["performed", "previous", item.exercise_id, performedId],
    queryFn: () => api.previousSets(item.exercise_id ?? "", performedId),
    enabled: item.exercise_id != null,
  });
  const fields = weightFields(item.weight_type);
  const options = exercises.some((exercise) => exercise.id === item.exercise_id)
    ? exercises
    : [{ id: item.exercise_id ?? "", name: item.name }, ...exercises];

  return (
    <section
      aria-label={`Упражнение ${index + 1}: ${item.name}`}
      className="flex flex-col gap-3 rounded-xl border border-slate-200 p-3 dark:border-slate-800"
    >
      <ProgressionHintCard
        exerciseId={item.exercise_id}
        performedId={performedId}
        onApplied={(result) => {
          if (result.set_id && result.weight != null) onAppliedWeight(result.set_id, result.weight);
        }}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-medium">{item.name}</h2>
        {item.exercise_id && (
          <Link
            to={`/exercises/${item.exercise_id}`}
            className={`${buttonClass} inline-flex items-center`}
          >
            Карточка
          </Link>
        )}
      </div>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Заменить упражнение
        <select
          aria-label={`Заменить упражнение ${item.name}`}
          className={inputClass}
          value={item.exercise_id ?? ""}
          onChange={(event) => onReplace(event.target.value)}
        >
          {options.map((exercise) => (
            <option key={exercise.id} value={exercise.id}>
              {exercise.name}
            </option>
          ))}
        </select>
      </label>

      {item.sets.map((logged, setIndex) => {
        const previousSet = previous.data?.sets[setIndex];
        const prior = setIndex > 0 ? item.sets[setIndex - 1] : undefined;
        const plan = targetLabel(item.targets[setIndex]);
        return (
          <div
            key={logged.id}
            role="group"
            aria-label={`Подход ${setIndex + 1}`}
            className="flex flex-col gap-2 rounded-lg bg-slate-100 p-2 dark:bg-slate-900"
          >
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-medium">Подход {setIndex + 1}</h3>
              {plan && <p className="text-xs text-slate-600 dark:text-slate-300">План: {plan}</p>}
            </div>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                className={buttonClass}
                disabled={!previousSet}
                onClick={() => previousSet && onChangeSet(logged.id, copiedLoad(previousSet))}
              >
                Как в прошлый раз
              </button>
              <button
                type="button"
                className={buttonClass}
                disabled={!prior}
                onClick={() => prior && onChangeSet(logged.id, copiedLoad(prior))}
              >
                Как в прошлом подходе
              </button>
            </div>
            {fields.weight && (
              <WeightField
                label={`${item.name}, подход ${setIndex + 1}: ${fields.weight}`}
                value={logged.weight}
                onChange={(weight) => onChangeSet(logged.id, { weight })}
              />
            )}
            {fields.extra && (
              <WeightField
                label={`${item.name}, подход ${setIndex + 1}: ${fields.extra}`}
                value={logged.extra_weight}
                onChange={(extra_weight) => onChangeSet(logged.id, { extra_weight })}
              />
            )}
            <NumberField
              label={`${item.name}, подход ${setIndex + 1}: повторы`}
              value={logged.reps}
              step={1}
              inputMode="numeric"
              onChange={(reps) => onChangeSet(logged.id, { reps })}
            />
            <div role="group" aria-label={`${item.name}, подход ${setIndex + 1}: RIR`} className="flex flex-wrap gap-1">
              {RIR_VALUES.map((value) => (
                <button
                  key={value}
                  type="button"
                  aria-pressed={logged.rir === value}
                  className={`${stepButtonClass} ${logged.rir === value ? "bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900" : ""}`}
                  onClick={() => onChangeSet(logged.id, { rir: logged.rir === value ? null : value })}
                >
                  {rirLabel(value)}
                </button>
              ))}
            </div>
            <div className="flex flex-col gap-1">
              <Flag
                label="Разминка"
                checked={logged.is_warmup}
                onChange={(is_warmup) => onChangeSet(logged.id, { is_warmup })}
              />
              <Flag
                label="С помощью"
                checked={logged.is_assisted}
                onChange={(is_assisted) => onChangeSet(logged.id, { is_assisted })}
              />
              <Flag
                label="Негативы"
                checked={logged.is_negative}
                onChange={(is_negative) => onChangeSet(logged.id, { is_negative })}
              />
            </div>
            <input
              aria-label={`${item.name}, подход ${setIndex + 1}: заметка`}
              className={inputClass}
              placeholder="Заметка к подходу"
              maxLength={500}
              value={logged.note ?? ""}
              onChange={(event) => onChangeSet(logged.id, { note: event.target.value || null })}
            />
            {pendingDelete === logged.id ? (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-sm">Удалить подход?</span>
                <button type="button" className={`${buttonClass} text-red-600`} onClick={() => onDelete(logged)}>
                  Удалить
                </button>
                <button type="button" className={buttonClass} onClick={onCancelDelete}>
                  Отмена
                </button>
              </div>
            ) : (
              <button type="button" className={`${buttonClass} self-start text-red-600`} onClick={() => onAskDelete(logged.id)}>
                Удалить подход
              </button>
            )}
          </div>
        );
      })}

      <button type="button" className={`${buttonClass} self-start border border-slate-300 dark:border-slate-700`} onClick={onAddSet}>
        Добавить подход
      </button>
      <label className="flex flex-col gap-1 text-sm font-medium">
        Заметка к упражнению
        <textarea
          aria-label={`Заметка к упражнению ${item.name}`}
          className={`${inputClass} min-h-20 py-2`}
          maxLength={2000}
          value={item.note ?? ""}
          onChange={(event) => onNote(event.target.value)}
        />
      </label>
    </section>
  );
}

function WeightField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  useEffect(() => {
    setDraft(null);
  }, [value]);
  const shown = draft ?? (value == null ? "" : formatWeightInput(value));
  const commit = (raw: string) => {
    if (raw.trim() === "") onChange(null);
    else {
      const parsed = parseDecimal(raw);
      if (parsed != null) onChange(parsed);
    }
  };
  return (
    <label className="flex flex-col gap-1 text-sm font-medium">
      {label.split(": ").at(-1)}
      <input
        data-log-field
        inputMode="decimal"
        autoComplete="off"
        aria-label={label}
        className={`${inputClass} w-full`}
        value={shown}
        onChange={(event) => {
          const raw = event.target.value;
          if (!decimalDraft(raw)) return;
          setDraft(raw);
          if (/[.,]$/.test(raw)) return;
          commit(raw);
        }}
        onBlur={() => {
          if (draft != null) commit(draft);
          setDraft(null);
        }}
        onKeyDown={(event) => {
          if (event.key !== "Enter") return;
          event.preventDefault();
          moveFocus(event.currentTarget, 1);
        }}
      />
    </label>
  );
}

function NumberField({
  label,
  value,
  step,
  inputMode,
  onChange,
}: {
  label: string;
  value: number | null;
  step: number;
  inputMode: "decimal" | "numeric";
  onChange: (value: number | null) => void;
}) {
  const parse = inputMode === "numeric" ? parseWhole : parseDecimal;
  return (
    <label className="flex flex-col gap-1 text-sm font-medium">
      {label.split(": ").at(-1)}
      <span className="flex items-center gap-1">
        <button
          type="button"
          className={stepButtonClass}
          aria-label={`${label}: меньше`}
          onClick={() => onChange(stepNumber(value, -1, step))}
        >
          −
        </button>
        <input
          data-log-field
          inputMode={inputMode}
          aria-label={label}
          className={`${inputClass} w-24 text-center`}
          value={value ?? ""}
          onChange={(event) => {
            if (event.target.value.trim() === "") onChange(null);
            else {
              const parsed = parse(event.target.value);
              if (parsed != null) onChange(parsed);
            }
          }}
          onKeyDown={(event) => {
            if (event.key !== "Enter") return;
            event.preventDefault();
            moveFocus(event.currentTarget, 1);
          }}
        />
        <button
          type="button"
          className={stepButtonClass}
          aria-label={`${label}: больше`}
          onClick={() => onChange(stepNumber(value, 1, step))}
        >
          +
        </button>
      </span>
    </label>
  );
}

function Flag({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
}) {
  return (
    <label className="flex min-h-11 items-center gap-2 text-sm">
      <input
        type="checkbox"
        className="size-5"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
      />
      {label}
    </label>
  );
}
