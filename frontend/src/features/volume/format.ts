import type { MuscleVolumeGroup } from "../../api/client";
import { labelFor, MUSCLE_OPTIONS } from "../exercises/options";

/** Ориентир для гипертрофии на группу за неделю. Это подсказка, а не запрет. */
export const TARGET_MIN = 10;
export const TARGET_MAX = 20;

type VolumeStatus = NonNullable<MuscleVolumeGroup["status"]>;

const STATUS_TEXT: Record<VolumeStatus, string> = {
  below: "ниже",
  in_range: "в ориентире",
  above: "выше",
};

const STATUS_BAR: Record<VolumeStatus, string> = {
  below: "bg-slate-500 dark:bg-slate-400",
  in_range: "bg-emerald-600 dark:bg-emerald-400",
  above: "bg-amber-600 dark:bg-amber-400",
};

export const NO_GROUP_TITLE = "Без группы";

export function groupTitle(group: MuscleVolumeGroup): string {
  if (group.muscle === null) return NO_GROUP_TITLE;
  return labelFor(MUSCLE_OPTIONS, group.muscle);
}

export function statusText(status: VolumeStatus): string {
  return STATUS_TEXT[status];
}

export function statusBarClass(status: VolumeStatus): string {
  return STATUS_BAR[status];
}

/** Слово при числе: подход, подхода, подходов (1, 2–4, 5+ с исключением 11–14). */
export function setsWord(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  if (mod10 === 1 && mod100 !== 11) return "подход";
  if (mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)) return "подхода";
  return "подходов";
}

/** Общая шкала полос: не меньше верхней границы ориентира, чтобы он всегда был виден. */
export function barScale(groups: MuscleVolumeGroup[]): number {
  return Math.max(TARGET_MAX, ...groups.map((group) => group.sets));
}

export function percentOf(value: number, scale: number): number {
  return Math.min(100, (value / scale) * 100);
}
