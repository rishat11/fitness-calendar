const MONTH_MS = 30 * 24 * 60 * 60 * 1000;

function storageKey(userId: string): string {
  return `fitness-calendar.export-reminder-hidden-until.${userId}`;
}

/** Скрытие живёт в браузере: сервер по-прежнему считает, что копию пора обновить. */
export function reminderHidden(userId: string, now = Date.now()): boolean {
  const raw = localStorage.getItem(storageKey(userId));
  if (raw == null) {
    return false;
  }
  const until = Date.parse(raw);
  return Number.isFinite(until) && until > now;
}

export function hideReminder(userId: string, now = Date.now()): void {
  localStorage.setItem(storageKey(userId), new Date(now + MONTH_MS).toISOString());
}
