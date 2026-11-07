import { describe, expect, it } from "vitest";
import { applyParsed, buildScanInput, emptyDraft } from "./form";

describe("inbody form", () => {
  it("builds a scan and treats a comma as a decimal separator", () => {
    const draft = emptyDraft("2026-10-26");
    draft.measured_time = "08:30";
    draft.weight_kg = "84,7";
    draft.smm_kg = "43";
    draft.bfm_kg = "9,9";
    draft.pbf_percent = "11,7";
    draft.tbw_l = "54,8";
    draft.visceral_fat_level = "3";
    draft.bmr_kcal = "1985";

    expect(buildScanInput(draft)).toEqual({
      measured_on: "2026-10-26",
      measured_time: "08:30:00",
      weight_kg: 84.7,
      smm_kg: 43,
      bfm_kg: 9.9,
      pbf_percent: 11.7,
      tbw_l: 54.8,
      visceral_fat_level: 3,
      bmr_kcal: 1985,
    });
  });

  it("rejects an empty weight and a fat percent of zero", () => {
    const draft = emptyDraft("2026-10-26");
    draft.smm_kg = "43";
    draft.bfm_kg = "9,9";
    draft.pbf_percent = "11,7";
    draft.tbw_l = "54,8";
    draft.visceral_fat_level = "3";
    draft.bmr_kcal = "1985";
    expect(buildScanInput(draft)).toBeNull();

    draft.weight_kg = "84,7";
    draft.pbf_percent = "0";
    expect(buildScanInput(draft)).toBeNull();
  });

  it("keeps a field the pdf did not contain", () => {
    const draft = emptyDraft("2026-10-01");
    draft.tbw_l = "50";
    const next = applyParsed(draft, {
      measured_on: "2026-11-07",
      measured_time: "09:15:00",
      weight_kg: 84.7,
      smm_kg: 38.2,
      bfm_kg: 16.4,
      pbf_percent: 19.4,
      tbw_l: null,
      visceral_fat_level: 7,
      bmr_kcal: 1750,
      missing: ["tbw_l"],
    });
    expect(next.weight_kg).toBe("84,7");
    expect(next.tbw_l).toBe("50");
    expect(next.measured_time).toBe("09:15");
  });
});
