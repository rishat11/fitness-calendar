import type { Block, BlockInput, BlockWeekInput } from "../../api/client";
export const MAX_BLOCK_WEEKS = 12;
export const MIN_CYCLE_DAYS = 1;
export const MAX_CYCLE_DAYS = 14;
export const DEFAULT_CYCLE_DAYS = 7;
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

/** Подпись дня цикла: день 1 — первый день после даты старта, не день недели. */
export function dayLabel(index: number): string {
  return `День ${index + 1}`;
}

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
  /** Сколько дней в одном цикле. Расписание повторяется для каждого цикла. */
  cycleDays: number;
  weeks: WeekDraft[];
  /** Для каждого дня цикла: пусто, «отдых» или id тренировки из библиотеки. */
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

/** Меняет число недель: лишние с конца убираются, новые копируют параметры последней. */
export function resizeBlockWeeks(weeks: WeekDraft[], count: number): WeekDraft[] {
  const next = Math.min(MAX_BLOCK_WEEKS, Math.max(1, Math.trunc(count)));
  if (next === weeks.length) return weeks;
  if (weeks.length === 0) {
    return Array.from({ length: next }, () => emptyWeekDraft());
  }
  if (next < weeks.length) return weeks.slice(0, next);
  const source = weeks[weeks.length - 1];
  const added = Array.from({ length: next - weeks.length }, () => {
    keyCounter += 1;
    return { ...source, key: `week-${keyCounter}` };
  });
  return [...weeks, ...added];
}

function clampCycleDays(count: number): number {
  return Math.min(MAX_CYCLE_DAYS, Math.max(MIN_CYCLE_DAYS, Math.trunc(count)));
}

/** Меняет число дней в цикле, сохраняя уже выбранные дни с начала. */
export function resizeCycleDays(schedule: string[], count: number): string[] {
  const next = clampCycleDays(count);
  if (next === schedule.length) return schedule;
  if (next < schedule.length) return schedule.slice(0, next);
  return [...schedule, ...Array.from({ length: next - schedule.length }, () => EMPTY_CHOICE)];
}

export function emptyBlockDraft(): BlockDraft {
  return {
    name: "",
    cycleDays: DEFAULT_CYCLE_DAYS,
    weeks: [emptyWeekDraft()],
    schedule: resizeCycleDays([], DEFAULT_CYCLE_DAYS),
  };
}

/** Черновик для правки уже сохранённого блока. Недели идут по номеру, пустые дни остаются пустыми. */
export function draftFromBlock(block: Block): BlockDraft {
  const schedule = resizeCycleDays([], block.cycle_days || DEFAULT_CYCLE_DAYS);
  for (const item of block.schedule) {
    if (item.day_index < 0 || item.day_index >= schedule.length) continue;
    if (item.kind === "rest") {
      schedule[item.day_index] = REST_CHOICE;
    } else if (item.template_id) {
      schedule[item.day_index] = item.template_id;
    }
  }

  const weeks = [...block.weeks]
    .sort((left, right) => left.position - right.position)
    .map((week) => {
      keyCounter += 1;
      return {
        key: `week-${keyCounter}`,
        weekType: week.week_type,
        repMin: String(week.rep_min),
        repMax: String(week.rep_max),
        targetRir: String(week.target_rir),
        volumeMultiplier: String(week.volume_multiplier),
      };
    });

  return {
    name: block.name,
    cycleDays: schedule.length,
    weeks: weeks.length > 0 ? weeks : [emptyWeekDraft()],
    schedule,
  };
}

function parseInteger(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

function parseWeek(week: WeekDraft, position: number): BlockWeekInput | string {
  const label = `Цикл ${position}`;
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

  return { input: { name, cycle_days: draft.cycleDays, weeks, schedule } };
}