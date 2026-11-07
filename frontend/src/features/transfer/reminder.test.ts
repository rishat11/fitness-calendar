import { afterEach, describe, expect, it } from "vitest";
import { hideReminder, reminderHidden } from "./reminder";

describe("export reminder dismissal", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("stays hidden for 30 days and then shows again", () => {
    const now = Date.parse("2026-11-07T12:00:00Z");
    expect(reminderHidden("user-1", now)).toBe(false);

    hideReminder("user-1", now);

    expect(reminderHidden("user-1", now + 29 * 24 * 60 * 60 * 1000)).toBe(true);
    expect(reminderHidden("user-2", now)).toBe(false);
    expect(reminderHidden("user-1", now + 30 * 24 * 60 * 60 * 1000)).toBe(false);
  });
});
