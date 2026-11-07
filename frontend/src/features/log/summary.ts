import type { PerformedWorkout } from "../../api/client";

/** Та же формула, что на сервере: разминка и пустые подходы не входят, гравитрон не даёт килограммы. */
export function setLoad(
  weightType: string,
  weight: number | null,
  extraWeight: number | null,
): number | null {
  if (weightType === "bodyweight_assisted") return null;
  if (weight == null && extraWeight == null) return null;
  const primary = weight ?? 0;
  const extra = extraWeight ?? 0;
  if (weightType === "per_dumbbell") return primary * 2;
  if (weightType === "stack_plus_extra") return primary + extra;
  return primary;
}

export function summarize(workout: Pick<PerformedWorkout, "items">): {
  workingSets: number;
  volume: number;
  unit: string | null;
} {
  let workingSets = 0;
  let volume = 0;
  const units = new Set<string>();
  for (const item of workout.items) {
    for (const logged of item.sets) {
      if (logged.is_warmup || logged.reps == null) continue;
      workingSets += 1;
      const load = setLoad(item.weight_type, logged.weight, logged.extra_weight);
      if (load == null) continue;
      volume += load * logged.reps;
      units.add(item.weight_unit);
    }
  }
  return {
    workingSets,
    volume: Math.round(volume * 100) / 100,
    unit: units.size === 1 ? [...units][0] : null,
  };
}

export function formatVolume(volume: number, unit: string | null): string {
  const number = new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 2 }).format(volume);
  if (unit === "kg") return `${number} кг`;
  if (unit === "lb") return `${number} lb`;
  return number;
}

export function moveFocus(current: HTMLElement, direction: 1 | -1) {
  const fields = [...document.querySelectorAll<HTMLElement>("[data-log-field]")];
  const index = fields.indexOf(current);
  if (index === -1) return;
  fields[index + direction]?.focus();
}
