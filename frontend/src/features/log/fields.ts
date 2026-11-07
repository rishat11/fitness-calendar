import type { SetLog, SetWrite } from "../../api/client";

export function stepNumber(current: number | null, direction: -1 | 1, step: number): number {
  const next = (current ?? 0) + direction * step;
  return Math.max(0, Math.round(next * 100) / 100);
}

/** Черновик веса: пусто, целое или дробь с запятой либо точкой, пока человек ещё печатает. */
export function decimalDraft(raw: string): boolean {
  return /^\d{0,6}([.,]\d{0,2})?$/.test(raw);
}

export function formatWeightInput(value: number): string {
  return String(value).replace(".", ",");
}

export function parseDecimal(raw: string): number | null {
  const trimmed = raw.trim().replace(",", ".");
  if (!trimmed) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0) return null;
  return Math.round(value * 100) / 100;
}

export function parseWhole(raw: string): number | null {
  const trimmed = raw.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number(trimmed);
}

export function setWrite(logged: SetLog): SetWrite {
  return {
    weight: logged.weight,
    extra_weight: logged.extra_weight,
    reps: logged.reps,
    rir: logged.rir,
    is_warmup: logged.is_warmup,
    is_assisted: logged.is_assisted,
    is_negative: logged.is_negative,
    note: logged.note,
  };
}

/** Вес, доп. вес, повторы и RIR. Признаки подхода не копируются: разминка не должна стать рабочей сама. */
export function copiedLoad(from: SetLog): Pick<SetLog, "weight" | "extra_weight" | "reps" | "rir"> {
  return {
    weight: from.weight,
    extra_weight: from.extra_weight,
    reps: from.reps,
    rir: from.rir,
  };
}

export function weightFields(weightType: string): { weight: string | null; extra: string | null } {
  switch (weightType) {
    case "per_dumbbell":
      return { weight: "Вес одной гантели", extra: null };
    case "stack":
      return { weight: "Стопка", extra: null };
    case "stack_plus_extra":
      return { weight: "Стопка", extra: "Доп. вес" };
    case "bodyweight_plus":
      return { weight: "Отягощение", extra: null };
    case "bodyweight_assisted":
      return { weight: "Помощь", extra: null };
    default:
      return { weight: "Вес", extra: null };
  }
}

export function rirLabel(value: number): string {
  return value >= 5 ? "4+" : String(value);
}

export function targetLabel(target: {
  rep_min: number;
  rep_max: number;
  target_rir: number | null;
} | undefined): string | null {
  if (!target) return null;
  const rir =
    target.target_rir == null ? "" : target.target_rir >= 5 ? ", RIR 4+" : `, RIR ${target.target_rir}`;
  return `${target.rep_min}–${target.rep_max}${rir}`;
}
