/**
 * Даты календаря: календарные строки YYYY-MM-DD без часового пояса.
 * Арифметика идёт через локальную полночь, поэтому сдвиги не зависят от пояса.
 */

const WEEKDAY_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
const LONG_DATE = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long", weekday: "long" });
const MONTH_TITLE = new Intl.DateTimeFormat("ru-RU", { month: "long", year: "numeric" });
const DATE_SHORT = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short", year: "numeric" });

export const WEEKDAY_LABELS = WEEKDAY_SHORT;

export function toIsoDate(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function parseIsoDate(iso: string): Date {
  const [year, month, day] = iso.split("-").map(Number);
  return new Date(year, month - 1, day);
}

export function todayIso(): string {
  return toIsoDate(new Date());
}

export function addDays(iso: string, days: number): string {
  const date = parseIsoDate(iso);
  date.setDate(date.getDate() + days);
  return toIsoDate(date);
}

/** Понедельник недели, в которую входит дата (неделя начинается с понедельника). */
export function mondayOf(iso: string): string {
  const weekday = (parseIsoDate(iso).getDay() + 6) % 7;
  return addDays(iso, -weekday);
}

export function weekDates(iso: string): string[] {
  const monday = mondayOf(iso);
  return Array.from({ length: 7 }, (_, index) => addDays(monday, index));
}

/** Шесть недель, которыми заполняется сетка месяца: от понедельника до конца сетки. */
export function monthGrid(year: number, month: number): string[] {
  const first = toIsoDate(new Date(year, month, 1));
  const start = mondayOf(first);
  return Array.from({ length: 42 }, (_, index) => addDays(start, index));
}

/** Первое число месяца, сдвинутого на `delta` месяцев от даты. */
export function addMonths(iso: string, delta: number): string {
  const date = parseIsoDate(iso);
  date.setDate(1);
  date.setMonth(date.getMonth() + delta);
  return toIsoDate(date);
}

export function isInMonth(iso: string, year: number, month: number): boolean {
  const date = parseIsoDate(iso);
  return date.getFullYear() === year && date.getMonth() === month;
}

export function monthOf(iso: string): { year: number; month: number } {
  const date = parseIsoDate(iso);
  return { year: date.getFullYear(), month: date.getMonth() };
}

export function formatMonthTitle(year: number, month: number): string {
  const title = MONTH_TITLE.format(new Date(year, month, 1));
  return title.charAt(0).toUpperCase() + title.slice(1);
}

export function formatLongDate(iso: string): string {
  return LONG_DATE.format(parseIsoDate(iso));
}

/** Заголовок недели: «2 нояб. 2026 г. – 8 нояб. 2026 г.». */
export function formatWeekTitle(days: string[]): string {
  const first = DATE_SHORT.format(parseIsoDate(days[0]));
  const last = DATE_SHORT.format(parseIsoDate(days[days.length - 1]));
  return `${first} – ${last}`;
}

/** Понедельник = 0, как в API (поле weekdays цикла). */
export function weekdayIndex(iso: string): number {
  return (parseIsoDate(iso).getDay() + 6) % 7;
}
