import type {
  Exercise,
  Workout,
  WorkoutInput,
  WorkoutItemInput,
  WorkoutSetInput,
} from "../../api/client";

export const MAX_ITEMS = 50;
export const MAX_SETS = 20;
const DEFAULT_SET_COUNT = 3;

/** Значения полей хранятся строками, как их вводит пользователь; в API уходят числа. */
export type SetDraft = {
  key: string;
  repMin: string;
  repMax: string;
  targetRir: string;
  restSeconds: string;
};

export type ItemDraft = {
  key: string;
  exerciseId: string;
  exercise: Pick<Exercise, "name" | "primary_muscle" | "equipment" | "archived">;
  sets: SetDraft[];
};

export type WorkoutDraft = {
  name: string;
  items: ItemDraft[];
};

let keyCounter = 0;
/** Ключи нужны только для React: не зависят от id на сервере, поэтому работают и для новых строк. */
function nextKey(): string {
  keyCounter += 1;
  return `row-${keyCounter}`;
}

export function newSetDraft(base?: Partial<Omit<SetDraft, "key">>): SetDraft {
  return {
    key: nextKey(),
    repMin: base?.repMin ?? "8",
    repMax: base?.repMax ?? "12",
    targetRir: base?.targetRir ?? "",
    restSeconds: base?.restSeconds ?? "",
  };
}

/** Новое упражнение получает подходы с диапазоном повторов из справочника. */
export function newItemDraft(exercise: Exercise): ItemDraft {
  const sets = Array.from({ length: DEFAULT_SET_COUNT }, () =>
    newSetDraft({
      repMin: String(exercise.rep_min),
      repMax: String(exercise.rep_max),
      targetRir: "",
      restSeconds: "",
    }),
  );
  return {
    key: nextKey(),
    exerciseId: exercise.id,
    exercise: {
      name: exercise.name,
      primary_muscle: exercise.primary_muscle,
      equipment: exercise.equipment,
      archived: exercise.archived,
    },
    sets,
  };
}

export function draftFromWorkout(workout: Workout): WorkoutDraft {
  return {
    name: workout.name,
    items: workout.items.map((item) => ({
      key: nextKey(),
      exerciseId: item.exercise_id,
      exercise: {
        name: item.exercise.name,
        primary_muscle: item.exercise.primary_muscle,
        equipment: item.exercise.equipment,
        archived: item.exercise.archived,
      },
      sets: item.sets.map((set) =>
        newSetDraft({
          repMin: String(set.rep_min),
          repMax: String(set.rep_max),
          targetRir: set.target_rir === null ? "" : String(set.target_rir),
          restSeconds: set.rest_seconds === null ? "" : String(set.rest_seconds),
        }),
      ),
    })),
  };
}

/** Содержимое черновика без служебных ключей React: по совпадению строк понятно, есть ли несохранённые правки. */
export function draftSignature(draft: WorkoutDraft): string {
  return JSON.stringify({
    name: draft.name,
    items: draft.items.map((item) => ({
      exerciseId: item.exerciseId,
      sets: item.sets.map(({ repMin, repMax, targetRir, restSeconds }) => ({
        repMin,
        repMax,
        targetRir,
        restSeconds,
      })),
    })),
  });
}

export function moveItem<T>(list: T[], index: number, delta: -1 | 1): T[] {
  const target = index + delta;
  if (target < 0 || target >= list.length) return list;
  const next = [...list];
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

function parseWhole(raw: string): number | null {
  const trimmed = raw.trim();
  return /^\d+$/.test(trimmed) ? Number(trimmed) : null;
}

function parseOptional(raw: string, min: number, max: number): number | "invalid" | null {
  if (raw.trim() === "") return null;
  const value = parseWhole(raw);
  return value === null || value < min || value > max ? "invalid" : value;
}

export type DraftValidation = {
  errors: string[];
  input: WorkoutInput | null;
};

/** Проверяет черновик так же, как API, и собирает тело запроса. Ошибки указывают место. */
export function validateDraft(draft: WorkoutDraft): DraftValidation {
  const errors: string[] = [];
  const name = draft.name.trim();
  if (name === "") errors.push("Укажите название тренировки");
  if (name.length > 120) errors.push("Название не длиннее 120 символов");

  if (draft.items.length > MAX_ITEMS) errors.push(`Упражнений не больше ${MAX_ITEMS}`);

  const items: WorkoutItemInput[] = [];
  draft.items.forEach((item) => {
    const label = `«${item.exercise.name}»`;
    if (item.sets.length === 0) errors.push(`${label}: добавьте хотя бы один подход`);
    if (item.sets.length > MAX_SETS) errors.push(`${label}: подходов не больше ${MAX_SETS}`);

    const sets: WorkoutSetInput[] = [];
    item.sets.forEach((set, index) => {
      const where = `${label}, подход ${index + 1}`;
      const repMin = parseWhole(set.repMin);
      const repMax = parseWhole(set.repMax);
      if (repMin === null || repMax === null || repMin < 1 || repMax > 100 || repMin > repMax) {
        errors.push(`${where}: повторы от 1 до 100, нижняя граница не больше верхней`);
      }

      const rir = parseOptional(set.targetRir, 0, 5);
      if (rir === "invalid") errors.push(`${where}: RIR от 0 до 5`);

      const rest = parseOptional(set.restSeconds, 0, 1800);
      if (rest === "invalid") errors.push(`${where}: отдых от 0 до 1800 секунд`);

      if (repMin !== null && repMax !== null && rir !== "invalid" && rest !== "invalid") {
        sets.push({ rep_min: repMin, rep_max: repMax, target_rir: rir, rest_seconds: rest });
      }
    });
    items.push({ exercise_id: item.exerciseId, sets });
  });

  if (errors.length > 0) return { errors, input: null };
  return { errors, input: { name, items } };
}
