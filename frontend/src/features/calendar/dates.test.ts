import { describe, expect, it } from "vitest";
import {
  addDays,
  addMonths,
  formatMonthTitle,
  isInMonth,
  mondayOf,
  monthGrid,
  parseIsoDate,
  toIsoDate,
  weekDates,
  weekdayIndex,
} from "./dates";

describe("calendar dates", () => {
  it("round-trips ISO dates without timezone shifts", () => {
    expect(toIsoDate(parseIsoDate("2026-11-06"))).toBe("2026-11-06");
    expect(toIsoDate(parseIsoDate("2026-03-01"))).toBe("2026-03-01");
  });

  it("adds days across month and year boundaries", () => {
    expect(addDays("2026-11-30", 1)).toBe("2026-12-01");
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-11-06", -6)).toBe("2026-10-31");
  });

  it("starts weeks on Monday", () => {
    // 2026-11-06 — пятница, понедельник той же недели — 2 ноября.
    expect(mondayOf("2026-11-06")).toBe("2026-11-02");
    // Воскресенье относится к неделе, которая начинается в понедельник перед ним.
    expect(mondayOf("2026-11-08")).toBe("2026-11-02");
    expect(weekDates("2026-11-06")).toEqual([
      "2026-11-02",
      "2026-11-03",
      "2026-11-04",
      "2026-11-05",
      "2026-11-06",
      "2026-11-07",
      "2026-11-08",
    ]);
  });

  it("maps weekdays to Monday-first indexes", () => {
    expect(weekdayIndex("2026-11-02")).toBe(0);
    expect(weekdayIndex("2026-11-06")).toBe(4);
    expect(weekdayIndex("2026-11-08")).toBe(6);
  });

  it("builds a six-week month grid that covers the whole month", () => {
    // Ноябрь 2026 начинается в воскресенье, поэтому сетка начнётся с 26 октября.
    const grid = monthGrid(2026, 10);
    expect(grid).toHaveLength(42);
    expect(grid[0]).toBe("2026-10-26");
    expect(grid[41]).toBe("2026-12-06");
    expect(grid.filter((iso) => isInMonth(iso, 2026, 10))).toHaveLength(30);
  });

  it("moves by whole months from the first day", () => {
    expect(addMonths("2026-01-31", 1)).toBe("2026-02-01");
    expect(addMonths("2026-11-06", -1)).toBe("2026-10-01");
    expect(addMonths("2026-12-15", 1)).toBe("2027-01-01");
  });

  it("formats the month title in Russian", () => {
    expect(formatMonthTitle(2026, 10)).toBe("Ноябрь 2026 г.");
  });
});
