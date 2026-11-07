import { ApiError } from "../../api/client";

export type OutboxMethod = "POST" | "PUT" | "PATCH" | "DELETE";

export type OutboxOp = {
  dedupeKey: string;
  method: OutboxMethod;
  path: string;
  body: unknown;
};

const STORAGE_KEY = "fc-performed-outbox";

let inflightKey: string | null = null;
let flushing = false;
let queuedAgain = false;

export function readOutbox(): OutboxOp[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(isOp);
  } catch {
    return [];
  }
}

function isOp(value: unknown): value is OutboxOp {
  if (typeof value !== "object" || value === null) return false;
  const op = value as OutboxOp;
  return typeof op.dedupeKey === "string" && typeof op.method === "string" && typeof op.path === "string";
}

function write(ops: OutboxOp[]) {
  if (ops.length === 0) localStorage.removeItem(STORAGE_KEY);
  else localStorage.setItem(STORAGE_KEY, JSON.stringify(ops));
}

/** Последняя операция с тем же ключом заменяет предыдущую: в очереди остаётся актуальное состояние. */
export function enqueue(op: OutboxOp) {
  const ops = readOutbox().filter((item) => item.dedupeKey !== op.dedupeKey);
  ops.push(op);
  write(ops);
}

/**
 * Удаление подхода. Если подход ещё не ушёл на сервер, из очереди убирается и его создание:
 * отправлять удаление нечего.
 */
export function queueSetDelete(setId: string, path: string) {
  const ops = readOutbox();
  const pendingCreate = ops.some((op) => op.dedupeKey === `add:${setId}`);
  const next = ops.filter(
    (op) =>
      op.dedupeKey !== `set:${setId}` &&
      op.dedupeKey !== `add:${setId}` &&
      op.dedupeKey !== `del:${setId}`,
  );
  if (!pendingCreate) {
    next.push({ dedupeKey: `del:${setId}`, method: "DELETE", path, body: null });
  }
  write(next);
}

/** Отмена удаления, пока запрос ещё не ушёл. `inflight` — сервер уже получает DELETE, подход нужно создать заново. */
export function cancelPendingDelete(setId: string): "cancelled" | "inflight" | "absent" {
  if (inflightKey === `del:${setId}`) return "inflight";
  const ops = readOutbox();
  if (!ops.some((op) => op.dedupeKey === `del:${setId}`)) return "absent";
  write(ops.filter((op) => op.dedupeKey !== `del:${setId}`));
  return "cancelled";
}

export function removeIfUnchanged(dedupeKey: string, body: unknown) {
  const ops = readOutbox();
  const current = ops.find((op) => op.dedupeKey === dedupeKey);
  if (!current) return;
  if (JSON.stringify(current.body) === JSON.stringify(body)) {
    write(ops.filter((op) => op.dedupeKey !== dedupeKey));
  }
}

export function isRetryable(error: unknown): boolean {
  if (error instanceof TypeError) return true;
  if (error instanceof ApiError) return error.status >= 500;
  return false;
}

/** Отправляет очередь по порядку. Обрыв сети оставляет операции на месте. */
export async function flushOutbox(send: (op: OutboxOp) => Promise<void>): Promise<void> {
  if (flushing) {
    queuedAgain = true;
    return;
  }
  flushing = true;
  try {
    do {
      queuedAgain = false;
      for (;;) {
        const op = readOutbox()[0];
        if (!op) break;
        inflightKey = op.dedupeKey;
        try {
          await send(op);
          removeIfUnchanged(op.dedupeKey, op.body);
        } finally {
          inflightKey = null;
        }
      }
    } while (queuedAgain && readOutbox().length > 0);
  } finally {
    flushing = false;
  }
}

export function clearOutbox() {
  write([]);
  inflightKey = null;
  flushing = false;
  queuedAgain = false;
}
