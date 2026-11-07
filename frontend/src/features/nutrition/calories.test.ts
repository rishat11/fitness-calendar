import { describe, expect, it } from "vitest";
import { formatCalories, macroCalories, parseGrams } from "./calories";

describe("macroCalories", () => {
  it("uses 4 kcal for protein and carbs and 9 kcal for fat", () => {
    expect(macroCalories({ protein: 100, carbs: 200, fat: 50 })).toBe(1650);
    expect(macroCalories({ protein: 10.1, carbs: 10.3, fat: 10.2 })).toBe(173.4);
    expect(macroCalories({ protein: 0, carbs: 0, fat: 0 })).toBe(0);
  });

  it("formats whole calories without a fraction", () => {
    expect(formatCalories(1650)).toBe("1650");
    expect(formatCalories(173.4)).toBe("173,4");
  });

  it("reads a decimal with a comma", () => {
    expect(parseGrams("10,5")).toBe(10.5);
    expect(parseGrams("")).toBeNull();
    expect(parseGrams("-1")).toBeNull();
    expect(parseGrams("2001")).toBeNull();
  });
});
