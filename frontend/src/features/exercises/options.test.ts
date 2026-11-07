import { describe, expect, it } from "vitest";
import {
  ALLOWED_WEIGHT_TYPES,
  buildQuickExerciseInput,
  defaultWeightType,
  weightTypeOptionsFor,
} from "./options";

describe("weight type by equipment", () => {
  it("offers only the weight types that fit the equipment", () => {
    expect(weightTypeOptionsFor("barbell").map((option) => option.value)).toEqual(["standard"]);
    expect(weightTypeOptionsFor("cable").map((option) => option.value)).toEqual([
      "stack",
      "stack_plus_extra",
    ]);
  });

  it("quick-create always produces a valid pair", () => {
    for (const equipment of Object.keys(ALLOWED_WEIGHT_TYPES) as (keyof typeof ALLOWED_WEIGHT_TYPES)[]) {
      const input = buildQuickExerciseInput({
        name: "Тест",
        primaryMuscle: "chest",
        equipment,
        weightUnit: "kg",
      });
      expect(ALLOWED_WEIGHT_TYPES[equipment]).toContain(defaultWeightType(equipment));
      expect(input.weight_type).toBe(defaultWeightType(equipment));
    }
  });
});
