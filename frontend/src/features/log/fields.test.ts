import { describe, expect, it } from "vitest";
import { copiedLoad, parseDecimal, parseWhole, stepNumber, targetLabel } from "./fields";
import type { SetLog } from "../../api/client";

const SET: SetLog = {
  id: "s",
  position: 0,
  exercise_id: "e",
  weight: 80,
  extra_weight: 2.5,
  reps: 8,
  rir: 5,
  is_warmup: true,
  is_assisted: false,
  is_negative: true,
  note: "узко",
};

describe("log fields", () => {
  it("steps weight by the exercise increment and does not go below zero", () => {
    expect(stepNumber(null, 1, 2.5)).toBe(2.5);
    expect(stepNumber(2.5, -1, 2.5)).toBe(0);
    expect(stepNumber(0, -1, 2.5)).toBe(0);
  });

  it("accepts a comma as a decimal separator", () => {
    expect(parseDecimal("12,5")).toBe(12.5);
    expect(parseDecimal("")).toBeNull();
    expect(parseWhole("10")).toBe(10);
    expect(parseWhole("10.5")).toBeNull();
  });

  it("copies load without warmup and negative flags", () => {
    expect(copiedLoad(SET)).toEqual({ weight: 80, extra_weight: 2.5, reps: 8, rir: 5 });
  });

  it("describes the planned set", () => {
    expect(targetLabel({ rep_min: 8, rep_max: 12, target_rir: 5 })).toBe("8–12, RIR 4+");
    expect(targetLabel(undefined)).toBeNull();
  });
});
