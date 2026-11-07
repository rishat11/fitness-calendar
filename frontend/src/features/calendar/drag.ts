import { type DragEndEvent } from "@dnd-kit/core";
import { type PlanEntry } from "../../api/client";

export type DropMove = { id: string; date: string };

const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Что нужно перенести после отпускания карточки: запись и дата назначения.
 * Возвращает null, если переносить некуда: нет записи, цель — не дата, или запись уронили на свой день.
 */
export function dropMove(event: Pick<DragEndEvent, "active" | "over">): DropMove | null {
  const entry = event.active.data.current?.entry as PlanEntry | undefined;
  const target = event.over?.id;
  if (!entry || typeof target !== "string" || !ISO_DATE.test(target) || target === entry.date) {
    return null;
  }
  return { id: entry.id, date: target };
}
