import { describe, expect, it } from "vitest";
import type { Exercise, Workout } from "../../api/client";
import {
  draftFromWorkout,
  moveItem,
  newItemDraft,
  newSetDraft,
  validateDraft,
  type WorkoutDraft,
} from "./draft";

const BENCH: Exercise = {
  id: "ex-1",
  name: "Жим штанги лёжа",
  primary_muscle: "chest",
  secondary_muscles: ["triceps"],
  equipment: "barbell",
  weight_type: "standard",
  weight_unit: "kg",
  weight_step: 2.5,
  rep_min: 6,
  rep_max: 10,
  archived: false,
};

function draftWith(overrides: Partial<WorkoutDraft> = {}): WorkoutDraft {
  return {
    name: "День A",
    items: [newItemDraft(BENCH)],
    ...overrides,
  };
}

describe("newItemDraft", () => {
  it("creates three sets with the exercise's default rep range", () => {
    const item = newItemDraft(BENCH);

    expect(item.exerciseId).toBe("ex-1");
    expect(item.sets).toHaveLength(3);
    expect(item.sets.every((set) => set.repMin === "6" && set.repMax === "10")).toBe(true);
    expect(item.sets.every((set) => set.targetRir === "" && set.restSeconds === "")).toBe(true);
  });

  it("gives every row a unique key", () => {
    const keys = [...newItemDraft(BENCH).sets, newSetDraft()].map((set) => set.key);
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("validateDraft", () => {
  it("builds the request body with numbers and nulls for empty optional fields", () => {
    const draft = draftWith({ name: "  День A  " });
    draft.items[0].sets[0] = newSetDraft({
      repMin: "3",
      repMax: "5",
      targetRir: "0",
      restSeconds: "240",
    });

    const { errors, input } = validateDraft(draft);

    expect(errors).toEqual([]);
    expect(input).toEqual({
      name: "День A",
      items: [
        {
          exercise_id: "ex-1",
          sets: [
            { rep_min: 3, rep_max: 5, target_rir: 0, rest_seconds: 240 },
            { rep_min: 6, rep_max: 10, target_rir: null, rest_seconds: null },
            { rep_min: 6, rep_max: 10, target_rir: null, rest_seconds: null },
          ],
        },
      ],
    });
  });

  it("allows a workout without exercises", () => {
    const { errors, input } = validateDraft({ name: "Пустой", items: [] });
    expect(errors).toEqual([]);
    expect(input).toEqual({ name: "Пустой", items: [] });
  });

  it("requires a name", () => {
    const { errors, input } = validateDraft(draftWith({ name: "   " }));
    expect(errors).toEqual(["Укажите название тренировки"]);
    expect(input).toBeNull();
  });

  it("points at the exercise and set with a reversed rep range", () => {
    const draft = draftWith();
    draft.items[0].sets[1] = newSetDraft({ repMin: "12", repMax: "8" });

    const { errors, input } = validateDraft(draft);

    expect(errors).toEqual([
      "«Жим штанги лёжа», подход 2: повторы от 1 до 100, нижняя граница не больше верхней",
    ]);
    expect(input).toBeNull();
  });

  it("rejects RIR above 5 and rest above 1800 seconds", () => {
    const draft = draftWith();
    draft.items[0].sets[0] = newSetDraft({ targetRir: "6", restSeconds: "1801" });

    const { errors } = validateDraft(draft);

    expect(errors).toEqual([
      "«Жим штанги лёжа», подход 1: RIR от 0 до 5",
      "«Жим штанги лёжа», подход 1: отдых от 0 до 1800 секунд",
    ]);
  });

  it("rejects a non-numeric value instead of silently dropping it", () => {
    const draft = draftWith();
    draft.items[0].sets[0] = newSetDraft({ repMin: "восемь", repMax: "12" });

    expect(validateDraft(draft).input).toBeNull();
  });

  it("requires at least one set in every exercise", () => {
    const draft = draftWith();
    draft.items[0].sets = [];

    expect(validateDraft(draft).errors).toEqual(["«Жим штанги лёжа»: добавьте хотя бы один подход"]);
  });
});

describe("draftFromWorkout", () => {
  it("converts nulls to empty inputs and keeps set order", () => {
    const workout: Workout = {
      id: "w-1",
      name: "День B",
      items: [
        {
          id: "i-1",
          exercise_id: "ex-1",
          position: 0,
          exercise: {
            id: "ex-1",
            name: "Жим штанги лёжа",
            primary_muscle: "chest",
            equipment: "barbell",
            archived: false,
          },
          sets: [
            { id: "s-1", rep_min: 3, rep_max: 5, target_rir: 0, rest_seconds: 240 },
            { id: "s-2", rep_min: 8, rep_max: 12, target_rir: null, rest_seconds: null },
          ],
        },
      ],
    };

    const draft = draftFromWorkout(workout);

    expect(draft.name).toBe("День B");
    expect(draft.items[0].sets.map((set) => [set.repMin, set.targetRir, set.restSeconds])).toEqual([
      ["3", "0", "240"],
      ["8", "", ""],
    ]);
  });
});

describe("moveItem", () => {
  it("swaps neighbours and ignores moves past the ends", () => {
    expect(moveItem(["a", "b", "c"], 1, -1)).toEqual(["b", "a", "c"]);
    expect(moveItem(["a", "b", "c"], 1, 1)).toEqual(["a", "c", "b"]);
    expect(moveItem(["a", "b"], 0, -1)).toEqual(["a", "b"]);
    expect(moveItem(["a", "b"], 1, 1)).toEqual(["a", "b"]);
  });

  it("does not mutate the original list", () => {
    const original = ["a", "b"];
    moveItem(original, 0, 1);
    expect(original).toEqual(["a", "b"]);
  });
});
