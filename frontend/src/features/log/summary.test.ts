import { describe, expect, it } from "vitest";
import { formatRecord, formatVolume, summarize } from "./summary";
import type { PerformedItem } from "../../api/client";

function item(partial: Partial<PerformedItem> & Pick<PerformedItem, "sets" | "weight_type">): PerformedItem {
  return {
    id: "item",
    position: 0,
    exercise_id: "ex",
    name: "Жим",
    equipment: "barbell",
    weight_unit: "kg",
    weight_step: 2.5,
    note: null,
    targets: [],
    ...partial,
  };
}

function set(partial: Partial<PerformedItem["sets"][number]>): PerformedItem["sets"][number] {
  return {
    id: "s",
    position: 0,
    exercise_id: "ex",
    weight: null,
    extra_weight: null,
    reps: null,
    rir: null,
    is_warmup: false,
    is_assisted: false,
    is_negative: false,
    note: null,
    ...partial,
  };
}

describe("workout summary", () => {
  it("skips warmup and sets without reps", () => {
    const summary = summarize({
      items: [
        item({
          weight_type: "standard",
          sets: [
            set({ weight: 60, reps: 12, is_warmup: true }),
            set({ id: "work", weight: 100, reps: 8 }),
            set({ id: "empty", weight: 100 }),
          ],
        }),
      ],
    });

    expect(summary).toEqual({ workingSets: 1, volume: 800, unit: "kg" });
    expect(formatVolume(summary.volume, summary.unit)).toBe("800 кг");
  });

  it("doubles a dumbbell and leaves assisted work out of the tonnage", () => {
    const summary = summarize({
      items: [
        item({
          weight_type: "per_dumbbell",
          sets: [set({ weight: 24, reps: 10 })],
        }),
        item({
          id: "assist",
          weight_type: "bodyweight_assisted",
          sets: [set({ id: "a", weight: 40, reps: 6 })],
        }),
      ],
    });

    expect(summary).toEqual({ workingSets: 2, volume: 480, unit: "kg" });
  });
});

describe("personal record text", () => {
  const base = {
    exercise_id: "ex",
    name: "Жим",
    load: 100,
    reps: 8,
    epley_1rm: null,
    unit: "kg" as const,
  };

  it("names weight, reps at the same load, and epley", () => {
    expect(formatRecord({ ...base, kind: "weight" })).toBe("Жим: рекорд веса 100 кг");
    expect(formatRecord({ ...base, kind: "reps" })).toBe("Жим: рекорд повторов 8 при 100 кг");
    expect(formatRecord({ ...base, kind: "epley", epley_1rm: 126.67 })).toBe("Жим: рекорд 1ПМ 126,67 кг");
    expect(formatRecord({ ...base, kind: "reps", load: null })).toBe("Жим: рекорд повторов 8");
  });
});
