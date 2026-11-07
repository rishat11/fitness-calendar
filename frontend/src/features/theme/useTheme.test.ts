import { describe, expect, it } from "vitest";
import { nextThemePreference } from "./useTheme";

describe("nextThemePreference", () => {
  it("cycles system, light, dark and back, so «как в системе» is not lost", () => {
    expect(nextThemePreference("system")).toBe("light");
    expect(nextThemePreference("light")).toBe("dark");
    expect(nextThemePreference("dark")).toBe("system");
  });
});
