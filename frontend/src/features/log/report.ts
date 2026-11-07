import type { PerformedItem, PerformedWorkout, SetLog } from "../../api/client";
import { rirLabel } from "./fields";
import { formatVolume, setLoad } from "./summary";

export function formatDuration(startedAt: string, finishedAt: string | null): string | null {
  if (!finishedAt) return null;
  const ms = Date.parse(finishedAt) - Date.parse(startedAt);
  if (!Number.isFinite(ms) || ms < 0) return null;
  if (ms < 60_000) return "меньше минуты";
  const total = Math.round(ms / 60_000);
  const hours = Math.floor(total / 60);
  const minutes = total % 60;
  if (hours === 0) return `${minutes} мин`;
  if (minutes === 0) return `${hours} ч`;
  return `${hours} ч ${minutes} мин`;
}

function setTouched(logged: SetLog): boolean {
  return (
    logged.weight != null ||
    logged.extra_weight != null ||
    logged.reps != null ||
    logged.rir != null ||
    logged.is_warmup ||
    logged.is_assisted ||
    logged.is_negative ||
    Boolean(logged.note)
  );
}

function describeLoad(
  item: Pick<PerformedItem, "weight_type" | "weight_unit">,
  logged: Pick<SetLog, "weight" | "extra_weight">,
): string | null {
  if (item.weight_type === "bodyweight_assisted") {
    return logged.weight == null ? null : `помощь ${formatVolume(logged.weight, item.weight_unit)}`;
  }
  if (item.weight_type === "stack_plus_extra" && (logged.weight != null || logged.extra_weight != null)) {
    return `${formatVolume(logged.weight ?? 0, null)} + ${formatVolume(logged.extra_weight ?? 0, item.weight_unit)}`;
  }
  if (item.weight_type === "per_dumbbell" && logged.weight != null) {
    return `по ${formatVolume(logged.weight, item.weight_unit)}`;
  }
  if (logged.weight == null && logged.extra_weight == null) return null;
  return formatVolume(logged.weight ?? logged.extra_weight ?? 0, item.weight_unit);
}

/** Одна строка подхода: разминка, нагрузка, повторы, RIR и особые признаки. */
export function formatSetLine(
  item: Pick<PerformedItem, "weight_type" | "weight_unit">,
  logged: Pick<SetLog, "weight" | "extra_weight" | "reps" | "rir" | "is_warmup" | "is_assisted" | "is_negative">,
): string {
  const parts: string[] = [];
  if (logged.is_warmup) parts.push("Разминка");
  const load = describeLoad(item, logged);
  if (load && logged.reps != null) parts.push(`${load} × ${logged.reps}`);
  else if (load) parts.push(load);
  else if (logged.reps != null) parts.push(`${logged.reps} повт.`);
  if (logged.rir != null) parts.push(`RIR ${rirLabel(logged.rir)}`);
  if (logged.is_assisted) parts.push("с помощью");
  if (logged.is_negative) parts.push("негативы");
  return parts.join(" · ");
}

export type ReportSetLine = {
  id: string;
  text: string;
  note: string | null;
  warmup: boolean;
};

export type ExerciseReport = {
  id: string;
  name: string;
  note: string | null;
  workingSets: number;
  volume: number;
  unit: string | null;
  lines: ReportSetLine[];
};

export function buildExerciseReports(items: PerformedItem[]): ExerciseReport[] {
  return items.map((item) => {
    let workingSets = 0;
    let volume = 0;
    const lines: ReportSetLine[] = [];
    for (const logged of item.sets) {
      if (!setTouched(logged)) continue;
      const working = !logged.is_warmup && logged.reps != null;
      if (working) {
        workingSets += 1;
        const load = setLoad(item.weight_type, logged.weight, logged.extra_weight);
        if (load != null) volume += load * logged.reps!;
      }
      lines.push({
        id: logged.id,
        text: formatSetLine(item, logged),
        note: logged.note,
        warmup: logged.is_warmup,
      });
    }
    return {
      id: item.id,
      name: item.name,
      note: item.note,
      workingSets,
      volume: Math.round(volume * 100) / 100,
      unit: workingSets > 0 && volume > 0 ? item.weight_unit : null,
      lines,
    };
  });
}

export function reportTotals(workout: Pick<PerformedWorkout, "items">): {
  workingSets: number;
  volume: number;
  unit: string | null;
} {
  const exercises = buildExerciseReports(workout.items);
  const units = new Set(exercises.map((exercise) => exercise.unit).filter((unit) => unit != null));
  return {
    workingSets: exercises.reduce((sum, exercise) => sum + exercise.workingSets, 0),
    volume: Math.round(exercises.reduce((sum, exercise) => sum + exercise.volume, 0) * 100) / 100,
    unit: units.size === 1 ? [...units][0] : null,
  };
}
