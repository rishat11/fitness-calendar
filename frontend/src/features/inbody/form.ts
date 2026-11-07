import type { InbodyParse, InbodyScanInput } from "../../api/client";

export type ScanDraft = {
  measured_on: string;
  measured_time: string;
  weight_kg: string;
  smm_kg: string;
  bfm_kg: string;
  pbf_percent: string;
  tbw_l: string;
  visceral_fat_level: string;
  bmr_kcal: string;
};

export function emptyDraft(today: string): ScanDraft {
  return {
    measured_on: today,
    measured_time: "",
    weight_kg: "",
    smm_kg: "",
    bfm_kg: "",
    pbf_percent: "",
    tbw_l: "",
    visceral_fat_level: "",
    bmr_kcal: "",
  };
}

export function draftFromScan(scan: InbodyScanInput & { measured_time?: string | null }): ScanDraft {
  return {
    measured_on: scan.measured_on,
    measured_time: scan.measured_time ? scan.measured_time.slice(0, 5) : "",
    weight_kg: String(scan.weight_kg).replace(".", ","),
    smm_kg: String(scan.smm_kg).replace(".", ","),
    bfm_kg: String(scan.bfm_kg).replace(".", ","),
    pbf_percent: String(scan.pbf_percent).replace(".", ","),
    tbw_l: String(scan.tbw_l).replace(".", ","),
    visceral_fat_level: String(scan.visceral_fat_level),
    bmr_kcal: String(scan.bmr_kcal),
  };
}

const PARSE_FIELD_LABELS: Record<string, string> = {
  measured_on: "дата",
  weight_kg: "вес",
  smm_kg: "мышцы",
  bfm_kg: "содержание жира",
  pbf_percent: "процент жира",
  tbw_l: "вода",
  visceral_fat_level: "висцеральный жир",
  bmr_kcal: "обмен веществ",
};

export function missingFieldLabel(code: string): string {
  return PARSE_FIELD_LABELS[code] ?? code;
}

function sheetNumber(value: number | null, current: string): string {
  if (value == null) return current;
  return String(value).replace(".", ",");
}

/** Подставляет прочитанные цифры и не затирает то, чего в PDF не было. */
export function applyParsed(draft: ScanDraft, parsed: InbodyParse): ScanDraft {
  return {
    ...draft,
    measured_on: parsed.measured_on ?? draft.measured_on,
    measured_time: parsed.measured_time ? parsed.measured_time.slice(0, 5) : draft.measured_time,
    weight_kg: sheetNumber(parsed.weight_kg, draft.weight_kg),
    smm_kg: sheetNumber(parsed.smm_kg, draft.smm_kg),
    bfm_kg: sheetNumber(parsed.bfm_kg, draft.bfm_kg),
    pbf_percent: sheetNumber(parsed.pbf_percent, draft.pbf_percent),
    tbw_l: sheetNumber(parsed.tbw_l, draft.tbw_l),
    visceral_fat_level:
      parsed.visceral_fat_level == null
        ? draft.visceral_fat_level
        : String(parsed.visceral_fat_level),
    bmr_kcal: parsed.bmr_kcal == null ? draft.bmr_kcal : String(parsed.bmr_kcal),
  };
}

export function parseMeasurement(
  raw: string,
  min: number,
  max: number,
  integer = false,
): number | null {
  const trimmed = raw.trim().replace(",", ".");
  if (trimmed === "") return null;
  if (integer) {
    if (!/^\d+$/.test(trimmed)) return null;
  } else if (!/^\d+(\.\d+)?$/.test(trimmed)) {
    return null;
  }
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < min || value > max) return null;
  return integer ? value : Math.round(value * 10) / 10;
}

export function buildScanInput(draft: ScanDraft): InbodyScanInput | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(draft.measured_on)) return null;
  const weight_kg = parseMeasurement(draft.weight_kg, 20, 400);
  const smm_kg = parseMeasurement(draft.smm_kg, 0, 200);
  const bfm_kg = parseMeasurement(draft.bfm_kg, 0, 300);
  const pbf_percent = parseMeasurement(draft.pbf_percent, 0.1, 80);
  const tbw_l = parseMeasurement(draft.tbw_l, 1, 200);
  const visceral_fat_level = parseMeasurement(draft.visceral_fat_level, 1, 30, true);
  const bmr_kcal = parseMeasurement(draft.bmr_kcal, 500, 6000, true);
  if (
    weight_kg == null ||
    smm_kg == null ||
    bfm_kg == null ||
    pbf_percent == null ||
    tbw_l == null ||
    visceral_fat_level == null ||
    bmr_kcal == null
  ) {
    return null;
  }
  let measured_time: string | null = null;
  const time = draft.measured_time.trim();
  if (time !== "") {
    if (!/^\d{2}:\d{2}$/.test(time)) return null;
    measured_time = `${time}:00`;
  }
  return {
    measured_on: draft.measured_on,
    measured_time,
    weight_kg,
    smm_kg,
    bfm_kg,
    pbf_percent,
    tbw_l,
    visceral_fat_level,
    bmr_kcal,
  };
}
