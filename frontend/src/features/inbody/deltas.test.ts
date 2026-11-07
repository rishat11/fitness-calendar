import { describe, expect, it } from "vitest";
import { formatDelta } from "./deltas";

describe("formatDelta", () => {
  it("shows kilograms and the relative percent", () => {
    expect(formatDelta({ absolute: 0.4, relative_percent: 0.5, unit: "kg" })).toBe("+0,4 кг (+0,5%)");
  });

  it("uses percentage points for body fat and levels for visceral fat", () => {
    expect(formatDelta({ absolute: 0.3, relative_percent: 2.6, unit: "pp" })).toBe("+0,3 п.п. (+2,6%)");
    expect(formatDelta({ absolute: -1, relative_percent: -33.3, unit: "level" })).toBe(
      "-1 ур. (-33,3%)",
    );
  });

  it("omits the percent when the previous value was zero", () => {
    expect(formatDelta({ absolute: 1, relative_percent: null, unit: "kg" })).toBe("+1 кг");
  });
});
