import { describe, expect, it } from "vitest";
import {
  addWeek,
  draftToInput,
  emptyBlockDraft,
  emptyWeekDraft,
  MAX_BLOCK_WEEKS,
  REST_CHOICE,
} from "./draft";

const TEMPLATE_ID = "11111111-1111-4111-8111-111111111111";

function filledDraft() {
  const draft = emptyBlockDraft();
  draft.name = "  Масса  ";
  draft.schedule[0] = TEMPLATE_ID;
  draft.schedule[2] = REST_CHOICE;
  return draft;
}

describe("draftToInput", () => {
  it("собирает тело запроса с числами и обрезанным названием", () => {
    const result = draftToInput(filledDraft());

    expect(result).toEqual({
      input: {
        name: "Масса",
        weeks: [
          {
            week_type: "hypertrophy",
            rep_min: 8,
            rep_max: 12,
            target_rir: 2,
            volume_multiplier: 1,
          },
          {
            week_type: "deload",
            rep_min: 8,
            rep_max: 12,
            target_rir: 4,
            volume_multiplier: 0.5,
          },
        ],
        schedule: [
          { day_index: 0, kind: "workout", template_id: TEMPLATE_ID },
          { day_index: 2, kind: "rest", template_id: null },
        ],
      },
    });
  });

  it("требует название", () => {
    const draft = filledDraft();
    draft.name = "   ";
    expect(draftToInput(draft)).toEqual({ error: "Укажите название блока" });
  });

  it("требует хотя бы одну тренировку в расписании", () => {
    const draft = emptyBlockDraft();
    draft.name = "Блок";
    draft.schedule[1] = REST_CHOICE;
    expect(draftToInput(draft)).toEqual({
      error: "Выберите хотя бы одну тренировку в расписании",
    });
  });

  it("отклоняет нижнюю границу повторов выше верхней", () => {
    const draft = filledDraft();
    draft.weeks[0] = { ...emptyWeekDraft(), repMin: "15", repMax: "10" };
    expect(draftToInput(draft)).toEqual({
      error: "Неделя 1: нижняя граница повторов больше верхней",
    });
  });

  it("принимает множитель с запятой и отклоняет ноль", () => {
    const draft = filledDraft();
    draft.weeks[0] = { ...emptyWeekDraft(), volumeMultiplier: "0,5" };
    const ok = draftToInput(draft);
    expect("input" in ok && ok.input.weeks[0].volume_multiplier).toBe(0.5);

    draft.weeks[0] = { ...emptyWeekDraft(), volumeMultiplier: "0" };
    expect(draftToInput(draft)).toEqual({
      error: "Неделя 1: множитель объёма больше 0 и не больше 1",
    });
  });

  it("по умолчанию ставит разгрузку последней и вставляет новую неделю перед ней", () => {
    const draft = emptyBlockDraft();
    expect(draft.weeks.map((week) => week.weekType)).toEqual(["hypertrophy", "deload"]);
    expect(draft.weeks[1].volumeMultiplier).toBe("0.5");
    expect(draft.weeks[1].targetRir).toBe("4");

    const added = addWeek(draft.weeks);
    expect(added.map((week) => week.weekType)).toEqual(["hypertrophy", "hypertrophy", "deload"]);
  });

  it("ограничивает число недель", () => {
    const draft = filledDraft();
    draft.weeks = Array.from({ length: MAX_BLOCK_WEEKS + 1 }, () => emptyWeekDraft());
    expect(draftToInput(draft)).toEqual({ error: `Не больше ${MAX_BLOCK_WEEKS} недель` });
  });
});