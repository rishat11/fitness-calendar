import { beforeEach, describe, expect, it } from "vitest";
import {
  cancelPendingDelete,
  clearOutbox,
  enqueue,
  flushOutbox,
  queueSetDelete,
  readOutbox,
} from "./outbox";

beforeEach(() => {
  clearOutbox();
});

describe("performed outbox", () => {
  it("keeps only the latest write for a set", () => {
    enqueue({ dedupeKey: "set:1", method: "PUT", path: "/sets/1", body: { reps: 8 } });
    enqueue({ dedupeKey: "set:1", method: "PUT", path: "/sets/1", body: { reps: 9 } });

    expect(readOutbox()).toEqual([
      { dedupeKey: "set:1", method: "PUT", path: "/sets/1", body: { reps: 9 } },
    ]);
  });

  it("drops a create that never reached the server when the set is deleted", () => {
    enqueue({ dedupeKey: "add:1", method: "POST", path: "/sets", body: { id: "1" } });
    enqueue({ dedupeKey: "set:1", method: "PUT", path: "/sets/1", body: { reps: 5 } });

    queueSetDelete("1", "/sets/1");

    expect(readOutbox()).toEqual([]);
  });

  it("cancels a queued delete so the set stays on the server", () => {
    queueSetDelete("1", "/sets/1");

    expect(cancelPendingDelete("1")).toBe("cancelled");
    expect(readOutbox()).toEqual([]);
    expect(cancelPendingDelete("1")).toBe("absent");
  });

  it("stops on a network error and continues later", async () => {
    enqueue({ dedupeKey: "set:1", method: "PUT", path: "/sets/1", body: { reps: 8 } });
    enqueue({ dedupeKey: "set:2", method: "PUT", path: "/sets/2", body: { reps: 6 } });
    let failed = true;

    await expect(
      flushOutbox(async () => {
        if (failed) throw new TypeError("Failed to fetch");
      }),
    ).rejects.toThrow(TypeError);
    expect(readOutbox()).toHaveLength(2);

    failed = false;
    const sent: string[] = [];
    await flushOutbox(async (op) => {
      sent.push(op.dedupeKey);
    });

    expect(sent).toEqual(["set:1", "set:2"]);
    expect(readOutbox()).toEqual([]);
  });
});
