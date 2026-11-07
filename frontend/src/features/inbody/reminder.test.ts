import { afterEach, describe, expect, it } from "vitest";
import { hideInbodyReminder, inbodyReminderHidden, scanReminderDue } from "./reminder";

describe("inbody reminder", () => {
  afterEach(() => {
    localStorage.clear();
  });

  it("is due without a scan and 14 days after the last one", () => {
    expect(scanReminderDue(null, "2026-11-07")).toBe(true);
    expect(scanReminderDue("2026-10-25", "2026-11-07")).toBe(false);
    expect(scanReminderDue("2026-10-24", "2026-11-07")).toBe(true);
  });

  it("stays hidden for 7 days and then shows again", () => {
    const now = Date.parse("2026-11-07T12:00:00Z");
    expect(inbodyReminderHidden("user-1", now)).toBe(false);

    hideInbodyReminder("user-1", now);

    expect(inbodyReminderHidden("user-1", now + 6 * 24 * 60 * 60 * 1000)).toBe(true);
    expect(inbodyReminderHidden("user-2", now)).toBe(false);
    expect(inbodyReminderHidden("user-1", now + 7 * 24 * 60 * 60 * 1000)).toBe(false);
  });
});
