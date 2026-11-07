import type { BlockInput, BlockWeekInput } from "../../api/client";
export const MAX_BLOCK_WEEKS = 12;
export const DAYS_IN_WEEK = 7;
export const REST_CHOICE = "rest";
export const EMPTY_CHOICE = "";

type WeekType = BlockWeekInput["week_type"];

export const WEEK_TYPE_LABELS: Record<WeekType, string> = {
  high_reps: "Высокие повторы",
  hypertrophy: "Гипертрофия",
  strength: "Сила",
  deload: "Разгрузка",
  free: "Свободная",
};

/** День расписания считается от даты старта блока: это день 1…7 недели, а не день недели. */
export const DAY_LABELS = Array.from({ length: DAYS_IN_WEEK }, (_, index) => `День ${index + 1}`);

/** Значения полей хранятся строками, как их вводит пользователь; в API уходят числа. */
export type WeekDraft = {
  key: string;
  weekType: WeekType;
  repMin: string;
  repMax: string;
  targetRir: string;
  volumeMultiplier: string;
};

export type BlockDraft = {
  name: string;
  weeks: WeekDraft[];
  /** Для каждого дня недели: пусто, «отдых» или id тренировки из библиотеки. */
  schedule: string[];
};

export type BlockDraftResult = { input: BlockInput } | { error: string };

let keyCounter = 0;

export function emptyWeekDraft(): WeekDraft {
  keyCounter += 1;
  return {
    key: `week-${keyCounter}`,
    weekType: "hypertrophy",
    repMin: "8",
    repMax: "12",
    targetRir: "2",
    volumeMultiplier: "1",
  };
}

export function emptyBlockDraft(): BlockDraft {
  return {
    name: "",
    weeks: [emptyWeekDraft()],
    schedule: Array.from({ length: DAYS_IN_WEEK }, () => EMPTY_CHOICE),
  };
}

function parseInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function parseWeek(week: WeekDraft, position: number): BlockWeekInput | string {
  const label = `Неделя ${position}`;
  const repMin = parseInteger(week.repMin);
  const repMax = parseInteger(week.repMax);
  const rir = parseInteger(week.targetRir);
  const multiplier = Number(week.volumeMultiplier.replace(",", "."));

  if (repMin === null || repMax === null || repMin < 1 || repMax > 30) {
    return `${label}: повторы от 1 до 30`;
  }
  if (repMin > repMax) {
    return `${label}: нижняя граница повторов больше верхней`;
  }
  if (rir === null || rir > 5) {
    return `${label}: RIR от 0 до 5`;
  }
  if (!(multiplier > 0 && multiplier <= 1)) {
    return `${label}: множитель объёма больше 0 и не больше 1`;
  }

  return {
    week_type: week.weekType,
    rep_min: repMin,
    rep_max: repMax,
    target_rir: rir,
    volume_multiplier: multiplier,
  };
}

/** Проверяет форму и собирает тело запроса. Ошибка возвращается текстом для пользователя. */
export function draftToInput(draft: BlockDraft): BlockDraftResult {
  const name = draft.name.trim();
  if (name === "") return { error: "Укажите название блока" };
  if (draft.weeks.length === 0) return { error: "Добавьте хотя бы одну неделю" };
  if (draft.weeks.length > MAX_BLOCK_WEEKS) {
    return { error: `Не больше ${MAX_BLOCK_WEEKS} недель` };
  }

  const weeks: BlockWeekInput[] = [];
  for (const [index, week] of draft.weeks.entries()) {
    const parsed = parseWeek(week, index + 1);
    if (typeof parsed === "string") return { error: parsed };
    weeks.push(parsed);
  }

  const schedule: BlockInput["schedule"] = [];
  draft.schedule.forEach((choice, dayIndex) => {
    if (choice === EMPTY_CHOICE) return;
    if (choice === REST_CHOICE) {
      schedule.push({ day_index: dayIndex, kind: "rest", template_id: null });
      return;
    }
    schedule.push({ day_index: dayIndex, kind: "workout", template_id: choice });
  });

  if (!schedule.some((item) => item.kind === "workout")) {
    return { error: "Выберите хотя бы одну тренировку в расписании" };
  }

  return { input: { name, weeks, schedule } };
}