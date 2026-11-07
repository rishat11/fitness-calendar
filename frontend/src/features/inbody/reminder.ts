const WEEK_MS = 7 * 24 * 60 * 60 * 1000;
const REMIND_AFTER_DAYS = 14;

function storageKey(userId: string): string {
  return `fitness-calendar.inbody-reminder-hidden-until.${userId}`;
}

function calendarDays(from: string, to: string): number {
  const [fromYear, fromMonth, fromDay] = from.split("-").map(Number);
  const [toYear, toMonth, toDay] = to.split("-").map(Number);
  const start = Date.UTC(fromYear, fromMonth - 1, fromDay);
  const end = Date.UTC(toYear, toMonth - 1, toDay);
  return Math.round((end - start) / (24 * 60 * 60 * 1000));
}

/** Нет замера или последнему уже 14 дней. */
export function scanReminderDue(latestOn: string | null, today: string): boolean {
  if (latestOn == null) return true;
  return calendarDays(latestOn, today) >= REMIND_AFTER_DAYS;
}

export function inbodyReminderHidden(userId: string, now = Date.now()): boolean {
  const raw = localStorage.getItem(storageKey(userId));
  if (raw == null) return false;
  const until = Date.parse(raw);
  return Number.isFinite(until) && until > now;
}

export function hideInbodyReminder(userId: string, now = Date.now()): void {
  localStorage.setItem(storageKey(userId), new Date(now + WEEK_MS).toISOString());
}
