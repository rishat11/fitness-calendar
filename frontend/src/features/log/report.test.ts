import { describe, expect, it } from "vitest";
import type { PerformedItem } from "../../api/client";
import { buildExerciseReports, formatDuration, formatSetLine, reportTotals } from "./report";

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

describe("workout report", () => {
  it("formats duration from start to finish", () => {
    expect(formatDuration("2026-11-10T10:00:00Z", "2026-11-10T11:00:00Z")).toBe("1 ч");
    expect(formatDuration("2026-11-10T10:00:00Z", "2026-11-10T11:12:00Z")).toBe("1 ч 12 мин");
    expect(formatDuration("2026-11-10T10:00:00Z", "2026-11-10T10:00:20Z")).toBe("меньше минуты");
    expect(formatDuration("2026-11-10T10:00:00Z", null)).toBeNull();
  });

  it("describes a working set, a warm-up and a dumbbell", () => {
    const bar = { weight_type: "standard", weight_unit: "kg" };
    expect(
      formatSetLine(bar, {
        weight: 100,
        extra_weight: null,
        reps: 8,
        rir: 2,
        is_warmup: false,
        is_assisted: false,
        is_negative: false,
      }),
    ).toBe("100 кг × 8 · RIR 2");
    expect(
      formatSetLine(bar, {
        weight: 60,
        extra_weight: null,
        reps: 10,
        rir: null,
        is_warmup: true,
        is_assisted: false,
        is_negative: false,
      }),
    ).toBe("Разминка · 60 кг × 10");
    expect(
      formatSetLine(
        { weight_type: "per_dumbbell", weight_unit: "kg" },
        {
          weight: 22.5,
          extra_weight: null,
          reps: 10,
          rir: 5,
          is_warmup: false,
          is_assisted: true,
          is_negative: false,
        },
      ),
    ).toBe("по 22,5 кг × 10 · RIR 4+ · с помощью");
  });

  it("sums working sets and skips an empty planned set", () => {
    const reports = buildExerciseReports([
      item({
        sets: [
          set({ id: "warm", weight: 60, reps: 10, is_warmup: true }),
          set({ id: "work", weight: 100, reps: 5, rir: 1 }),
          set({ id: "empty" }),
        ],
      }),
    ]);
    expect(reports[0].lines.map((line) => line.id)).toEqual(["warm", "work"]);
    expect(reports[0].workingSets).toBe(1);
    expect(reports[0].volume).toBe(500);
  });

  it("counts volume across exercises", () => {
    const bench = item({
      id: "bench",
      sets: [set({ id: "a", weight: 100, reps: 5 })],
    });
    const row = item({
      id: "row",
      name: "Тяга",
      weight_type: "per_dumbbell",
      sets: [set({ id: "b", weight: 20, reps: 10 })],
    });
    const totals = reportTotals({ items: [bench, row] });
    expect(totals.workingSets).toBe(2);
    expect(totals.volume).toBe(900);
    expect(totals.unit).toBe("kg");
  });
});
