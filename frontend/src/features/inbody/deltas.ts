import type { InbodyDelta } from "../../api/client";

const LABELS: Record<InbodyDelta["code"], string> = {
  weight_kg: "Вес",
  smm_kg: "Мышцы",
  bfm_kg: "Жир",
  pbf_percent: "Процент жира",
  tbw_l: "Вода",
  visceral_fat_level: "Висцеральный жир",
};

const UNITS: Record<InbodyDelta["unit"], string> = {
  kg: "кг",
  l: "л",
  pp: "п.п.",
  level: "ур.",
};

function formatNumber(value: number): string {
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits: 1 }).format(value);
}

function signed(value: number): string {
  const text = formatNumber(value);
  return value > 0 ? `+${text}` : text;
}

export function deltaLabel(code: InbodyDelta["code"]): string {
  return LABELS[code];
}

/** Абсолют и, если база не ноль, относительный процент. Знак у обоих чисел. */
export function formatDelta(delta: Pick<InbodyDelta, "absolute" | "relative_percent" | "unit">): string {
  const absolute = `${signed(delta.absolute)} ${UNITS[delta.unit]}`;
  if (delta.relative_percent == null) return absolute;
  return `${absolute} (${signed(delta.relative_percent)}%)`;
}
