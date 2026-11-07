import { type PlanEntry } from "../../api/client";

export type PlanStatus = NonNullable<PlanEntry["status"]>;

export const STATUS_OPTIONS: { value: PlanStatus; label: string }[] = [
  { value: "planned", label: "Запланирована" },
  { value: "done", label: "Выполнена" },
  { value: "skipped", label: "Пропущена" },
  { value: "moved", label: "Перенесена" },
];

/** Зеркало STATUS_TRANSITIONS на бэкенде: сервер остаётся главным, здесь только блокируем заведомо неверные кнопки. */
const TRANSITIONS: Record<PlanStatus, readonly PlanStatus[]> = {
  planned: ["done", "skipped", "moved"],
  done: ["planned"],
  skipped: ["planned"],
  moved: ["planned"],
};

export function canChangeStatus(from: PlanStatus, to: PlanStatus): boolean {
  return from === to || TRANSITIONS[from].includes(to);
}

export function statusLabel(status: PlanStatus): string {
  return STATUS_OPTIONS.find((option) => option.value === status)?.label ?? status;
}

export function entryTitle(entry: PlanEntry): string {
  return entry.kind === "rest" ? "Отдых" : (entry.name ?? "Тренировка");
}

/** День отдыха двигается, пока не зафиксирован. Тренировка — только в статусе «запланирована». */
export function canShift(entry: PlanEntry): boolean {
  if (entry.is_fixed) return false;
  if (entry.kind === "rest") return true;
  return entry.status === "planned";
}
