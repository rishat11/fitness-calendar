import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkoutEditorPage } from "./WorkoutEditorPage";

const PROFILE = {
  goal: null,
  height_cm: null,
  age: null,
  sex: null,
  weight_unit: "kg",
  theme: "system",
};

const BENCH = {
  id: "ex-bench",
  name: "Жим штанги лёжа",
  primary_muscle: "chest",
  secondary_muscles: ["triceps"],
  equipment: "barbell",
  weight_type: "standard",
  weight_unit: "kg",
  weight_step: 2.5,
  rep_min: 8,
  rep_max: 12,
};

const ROW = {
  id: "ex-row",
  name: "Тяга верхнего блока",
  primary_muscle: "back",
  secondary_muscles: [],
  equipment: "cable",
  weight_type: "stack",
  weight_unit: "kg",
  weight_step: 5,
  rep_min: 10,
  rep_max: 15,
};

/** Тренировка на сервере: два упражнения, у первого два разных подхода. */
const WORKOUT = {
  id: "w-1",
  name: "День A",
  items: [
    {
      id: "item-bench",
      exercise_id: BENCH.id,
      position: 0,
      exercise: {
        id: BENCH.id,
        name: BENCH.name,
        primary_muscle: "chest",
        equipment: "barbell",
      },
      sets: [
        { id: "s1", rep_min: 3, rep_max: 5, target_rir: 0, rest_seconds: 240 },
        { id: "s2", rep_min: 8, rep_max: 10, target_rir: null, rest_seconds: null },
      ],
    },
    {
      id: "item-row",
      exercise_id: ROW.id,
      position: 1,
      exercise: {
        id: ROW.id,
        name: ROW.name,
        primary_muscle: "back",
        equipment: "cable",
      },
      sets: [{ id: "s3", rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null }],
    },
  ],
};

let workout: typeof WORKOUT;
let exercises: (typeof BENCH)[];

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Имитация API: тренировка, список упражнений с поиском и сохранение (PUT) с ответом сервера. */
function handleRequest(url: string, init?: RequestInit): Response {
  const method = init?.method ?? "GET";
  const parsed = new URL(url, "http://localhost");
  const path = parsed.pathname;

  if (path === "/api/profile") return jsonResponse(PROFILE);
  if (path === "/api/exercises" && method === "GET") {
    const q = (parsed.searchParams.get("q") ?? "").toLowerCase();
    return jsonResponse(exercises.filter((item) => item.name.toLowerCase().includes(q)));
  }
  if (path === `/api/workouts/${workout.id}` && method === "GET") {
    return jsonResponse(workout);
  }
  if (path === `/api/workouts/${workout.id}` && method === "PUT") {
    const body = JSON.parse(init?.body as string);
    workout = {
      ...workout,
      name: body.name,
      items: body.items.map(
        (item: { exercise_id: string; sets: object[] }, position: number) => {
          const exercise = exercises.find((candidate) => candidate.id === item.exercise_id);
          return {
            id: `saved-${position}`,
            exercise_id: item.exercise_id,
            position,
            exercise: {
              id: exercise?.id,
              name: exercise?.name,
              primary_muscle: exercise?.primary_muscle,
              equipment: exercise?.equipment,
            },
            sets: item.sets.map((set, index) => ({ id: `saved-set-${index}`, ...set })),
          };
        },
      ),
    };
    return jsonResponse(workout);
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage(path = `/workouts/${WORKOUT.id}`, state?: { editing?: boolean }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[{ pathname: path, state }]}>
        <Routes>
          <Route path="/workouts/:workoutId" element={<WorkoutEditorPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function putCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "PUT");
}

function lastPutBody() {
  const calls = putCalls();
  return JSON.parse(calls[calls.length - 1][1]?.body as string);
}

/** Ждёт загрузки и возвращает строку первого упражнения. */
function firstItem() {
  return screen.findByRole("listitem", { name: "Упражнение 1: Жим штанги лёжа" });
}

async function openEditor(user: ReturnType<typeof userEvent.setup>) {
  await user.click(await screen.findByRole("button", { name: "Редактировать" }));
}

describe("WorkoutEditorPage", () => {
  beforeEach(() => {
    workout = structuredClone(WORKOUT);
    exercises = [BENCH, ROW];
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows exercises with their sets and keeps editing behind a button", async () => {
    renderPage();
    const first = await firstItem();

    expect(within(first).getByText("3–5 повт., RIR 0, отдых 240 с")).toBeInTheDocument();
    expect(within(first).getByText("8–10 повт.")).toBeInTheDocument();
    expect(
      screen.getByRole("listitem", { name: "Упражнение 2: Тяга верхнего блока" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Добавить упражнение" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Сохранить" })).toBeNull();
    expect(screen.queryByLabelText("Название тренировки")).toBeNull();
  });

  it("opens a just-created workout ready to add exercises", async () => {
    renderPage(`/workouts/${WORKOUT.id}`, { editing: true });

    expect(await screen.findByRole("button", { name: "Добавить упражнение" })).toBeInTheDocument();
    expect(screen.getByLabelText("Название тренировки")).toHaveValue("День A");
    expect(screen.queryByRole("button", { name: "Редактировать" })).toBeNull();
  });

  it("saves edited sets as numbers, with nulls for empty optional fields", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    const first = await firstItem();

    await user.type(within(first).getByLabelText("Жим штанги лёжа, подход 2: отдых, секунды"), "90");
    await user.selectOptions(within(first).getByLabelText("Жим штанги лёжа, подход 2: RIR"), "2");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Сохранено");
    expect(lastPutBody()).toEqual({
      name: "День A",
      items: [
        {
          exercise_id: BENCH.id,
          sets: [
            { rep_min: 3, rep_max: 5, target_rir: 0, rest_seconds: 240 },
            { rep_min: 8, rep_max: 10, target_rir: 2, rest_seconds: 90 },
          ],
        },
        {
          exercise_id: ROW.id,
          sets: [{ rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null }],
        },
      ],
    });
  });

  it("moves an exercise down and keeps the new order on save", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    await firstItem();

    await user.click(screen.getByRole("button", { name: "Опустить Жим штанги лёжа" }));
    expect(
      screen.getByRole("listitem", { name: "Упражнение 1: Тяга верхнего блока" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByRole("status");

    expect(
      lastPutBody().items.map((item: { exercise_id: string }) => item.exercise_id),
    ).toEqual([ROW.id, BENCH.id]);
  });

  it("adds a set that copies the previous one", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    const first = await firstItem();

    await user.click(within(first).getByRole("button", { name: "Добавить подход" }));
    expect(within(first).getByLabelText("Жим штанги лёжа, подход 3: повторы от")).toHaveValue("8");
    expect(within(first).getByLabelText("Жим штанги лёжа, подход 3: повторы до")).toHaveValue("10");

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByRole("status");
    expect(lastPutBody().items[0].sets).toHaveLength(3);
  });

  it("adds an exercise found in the reference list with its default rep range", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    await firstItem();

    expect(screen.queryByRole("form", { name: "Быстрое создание упражнения" })).toBeNull();
    expect(screen.queryByLabelText("Поиск в справочнике")).toBeNull();

    await user.click(screen.getByRole("button", { name: "Добавить упражнение" }));
    const picker = await screen.findByRole("list", { name: "Упражнения справочника" });
    expect(within(picker).getAllByRole("listitem")).toHaveLength(2);

    await user.type(screen.getByLabelText("Поиск в справочнике"), "Тяга");
    await waitFor(() => {
      expect(within(picker).getAllByRole("listitem")).toHaveLength(1);
    });
    await user.click(within(picker).getByRole("button", { name: "В тренировку" }));

    expect(
      screen.getByRole("listitem", { name: "Упражнение 3: Тяга верхнего блока" }),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByRole("status");

    const added = lastPutBody().items[2];
    expect(added.exercise_id).toBe(ROW.id);
    expect(added.sets).toEqual([
      { rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null },
      { rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null },
      { rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null },
      { rep_min: 10, rep_max: 15, target_rir: null, rest_seconds: null },
    ]);
  });

  it("does not send a request while a set has a reversed rep range", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    const first = await firstItem();

    const from = within(first).getByLabelText("Жим штанги лёжа, подход 2: повторы от");
    await user.clear(from);
    await user.type(from, "12");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));

    expect(screen.getByRole("alert")).toHaveTextContent(
      "«Жим штанги лёжа», подход 2: повторы от 1 до 100, нижняя граница не больше верхней",
    );
    expect(putCalls()).toHaveLength(0);
  });

  it("keeps at least one set for every exercise", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    await firstItem();
    const second = screen.getByRole("listitem", { name: "Упражнение 2: Тяга верхнего блока" });
    const removeOnly = within(second).getByRole("button", {
      name: "Убрать подход 1, Тяга верхнего блока",
    });

    expect(removeOnly).toBeDisabled();

    await user.click(within(second).getByRole("button", { name: "Добавить подход" }));
    expect(removeOnly).toBeEnabled();
  });

  it("clears validation errors once the user edits the form", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    const first = await firstItem();
    const from = within(first).getByLabelText("Жим штанги лёжа, подход 2: повторы от");
    await user.clear(from);
    await user.type(from, "12");
    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    expect(screen.getByRole("alert")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Название тренировки"), "!");

    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows unsaved changes and warns before leaving the page", async () => {
    const user = userEvent.setup();
    renderPage();
    await openEditor(user);
    const first = await firstItem();
    expect(screen.queryByText("Есть несохранённые изменения")).toBeNull();

    await user.type(within(first).getByLabelText("Жим штанги лёжа, подход 2: отдых, секунды"), "90");
    expect(screen.getByText("Есть несохранённые изменения")).toBeInTheDocument();

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await user.click(screen.getByRole("link", { name: "← Все тренировки" }));
    expect(confirm).toHaveBeenCalledTimes(1);
    confirm.mockRestore();

    await user.click(screen.getByRole("button", { name: "Сохранить" }));
    await screen.findByRole("status");
    expect(screen.queryByText("Есть несохранённые изменения")).toBeNull();
    const after = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(after);
    expect(after.defaultPrevented).toBe(false);
  });

  it("shows a message for a workout that does not exist", async () => {
    renderPage("/workouts/unknown");

    expect(await screen.findByRole("alert")).toHaveTextContent("Тренировка не найдена");
  });
});
