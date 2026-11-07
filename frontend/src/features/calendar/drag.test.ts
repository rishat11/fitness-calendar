import { type DragEndEvent } from "@dnd-kit/core";
import { describe, expect, it } from "vitest";
import { type PlanEntry } from "../../api/client";
import { dropMove } from "./drag";

const ENTRY = { id: "e1", date: "2026-11-10", kind: "workout" } as PlanEntry;

function event(entry: Partial<PlanEntry> | undefined, over: string | null): DragEndEvent {
  return {
    active: { id: "e1", data: { current: entry ? { entry: { ...ENTRY, ...entry } } : undefined } },
    over: over === null ? null : { id: over },
  } as unknown as DragEndEvent;
}

describe("dropMove", () => {
  it("moves the dragged entry to the day it was dropped on", () => {
    expect(dropMove(event({}, "2026-11-15"))).toEqual({ id: "e1", date: "2026-11-15" });
  });

  it("moves across months, since the target is a plain date", () => {
    expect(dropMove(event({}, "2026-12-01"))).toEqual({ id: "e1", date: "2026-12-01" });
  });

  it("does nothing when the entry is dropped outside a day", () => {
    expect(dropMove(event({}, null))).toBeNull();
  });

  it("does nothing when the entry is dropped on its own day", () => {
    expect(dropMove(event({}, "2026-11-10"))).toBeNull();
  });

  it("does nothing when the drag carries no entry", () => {
    expect(dropMove(event(undefined, "2026-11-15"))).toBeNull();
  });

  it("ignores targets that are not dates", () => {
    expect(dropMove(event({}, "week-45"))).toBeNull();
  });
});
