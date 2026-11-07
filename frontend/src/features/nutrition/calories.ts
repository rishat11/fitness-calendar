export type MacroGrams = {
  protein: number;
  carbs: number;
  fat: number;
};

/** Б×4 + У×4 + Ж×9, до одной десятой. Пока ответ сервера в пути, экран считает так же. */
export function macroCalories(grams: MacroGrams): number {
  const raw = grams.protein * 4 + grams.carbs * 4 + grams.fat * 9;
  return Math.round(raw * 10) / 10;
}

export function formatCalories(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(1).replace(".", ",");
}

/** Пустая строка и нечисло — null. Запятая считается десятичным разделителем. */
export function parseGrams(raw: string): number | null {
  const trimmed = raw.trim().replace(",", ".");
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value > 2000) return null;
  return Math.round(value * 10) / 10;
}

export function formatGrams(value: number | null): string {
  if (value == null) return "";
  return String(value).replace(".", ",");
}
