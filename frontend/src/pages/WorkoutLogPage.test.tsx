import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearOutbox, readOutbox } from "../features/log/outbox";
import { WorkoutLogPage } from "./WorkoutLogPage";

const BENCH = {
  id: "ex-1",
  name: "Жим штанги лёжа",
  primary_muscle: "chest",
  secondary_muscles: [],
  equipment: "barbell",
  weight_type: "standard",
  weight_unit: "kg",
  weight_step: 2.5,
  rep_min: 8,
  rep_max: 12,
};

function emptySet(id: string, position: number) {
  return {
    id,
    position,
    exercise_id: BENCH.id,
    weight: null,
    extra_weight: null,
    reps: null,
    rir: null,
    is_warmup: false,
    is_assisted: false,
    is_negative: false,
    note: null,
  };
}

const WORKOUT = {
  id: "perf-1",
  planned_id: "plan-1",
  date: "2026-11-10",
  name: "День A",
  note: null,
  started_at: "2026-11-10T10:00:00Z",
  finished_at: null,
  summary: { working_sets: 0, volume: 0, unit: null, records: [] },
  items: [
    {
      id: "item-1",
      position: 0,
      exercise_id: BENCH.id,
      name: BENCH.name,
      equipment: "barbell",
      weight_type: "standard",
      weight_unit: "kg",
      weight_step: 2.5,
      note: null,
      targets: [
        { rep_min: 8, rep_max: 12, target_rir: 2, rest_seconds: 90 },
        { rep_min: 8, rep_max: 12, target_rir: 2, rest_seconds: 90 },
      ],
      sets: [emptySet("s1", 0), emptySet("s2", 1)],
    },
  ],
};

const PREVIOUS = {
  performed_id: "perf-old",
  date: "2026-11-03",
  sets: [
    { ...emptySet("old-1", 0), weight: 100, reps: 8, rir: 1 },
    { ...emptySet("old-2", 1), weight: 100, reps: 6 },
  ],
};

let failPuts = false;
let progression: unknown = null;
let finishRecords: unknown[] = [];
const wakeRequest = vi.fn(async () => ({ release: vi.fn() }));

const INCREASE = {
  exercise_id: BENCH.id,
  status: "increase_weight",
  message: "Повысьте вес на шаг упражнения. После повышения ожидаются повторы около нижней границы.",
  suggested_weight: 102.5,
  weight_unit: "kg",
  last_session_id: "perf-old",
  epley_1rm: 140,
  week_type: "hypertrophy",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function handleRequest(url: string, init?: RequestInit): Response | Promise<Response> {
  const method = init?.method ?? "GET";
  const path = new URL(url, "http://localhost").pathname;
  if (method === "PUT") {
    if (failPuts) return Promise.reject(new TypeError("Failed to fetch"));
    return jsonResponse({ id: path.split("/").at(-1), position: 0, exercise_id: BENCH.id, ...JSON.parse(String(init?.body)) });
  }
  if (path === "/api/performed" && method === "POST") return jsonResponse(WORKOUT);
  if (path === "/api/performed/previous") return jsonResponse(PREVIOUS);
  if (path.startsWith("/api/progression/") && method === "GET") return jsonResponse(progression);
  if (path.endsWith("/decision") && method === "POST") {
    progression = null;
    return jsonResponse({
      action: "accept",
      performed_id: WORKOUT.id,
      set_id: "s1",
      weight: 102.5,
    });
  }
  if (path === "/api/exercises") return jsonResponse([BENCH]);
  if (method === "DELETE") return new Response(null, { status: 204 });
  if (path.endsWith("/finish")) {
    return jsonResponse({
      ...WORKOUT,
      finished_at: "2026-11-10T11:00:00Z",
      summary: { working_sets: 1, volume: 250, unit: "kg", records: finishRecords },
    });
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/log/plan-1"]}>
        <Routes>
          <Route path="/log/:plannedId" element={<WorkoutLogPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WorkoutLogPage", () => {
  beforeEach(() => {
    failPuts = false;
    progression = null;
    finishRecords = [];
    clearOutbox();
    wakeRequest.mockClear();
    Object.defineProperty(navigator, "wakeLock", {
      configurable: true,
      value: { request: wakeRequest },
    });
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)));
  });

  afterEach(() => {
    clearOutbox();
    vi.unstubAllGlobals();
  });

  it("shows a progression hint before the exercise and accepts the suggested weight", async () => {
    progression = INCREASE;
    const user = userEvent.setup();
    renderPage();
    const exercise = await screen.findByRole("region", { name: "Упражнение 1: Жим штанги лёжа" });
    const hint = await within(exercise).findByRole("region", { name: "Подсказка по прогрессии" });
    const heading = within(exercise).getByRole("heading", { name: "Жим штанги лёжа" });

    expect(hint).toHaveTextContent("Повысьте вес на шаг упражнения");
    expect(hint).toHaveTextContent("Тип недели: Гипертрофия");
    expect(hint).toHaveTextContent("102,5");
    expect(hint.compareDocumentPosition(heading) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    await user.click(within(hint).getByRole("button", { name: "Принять" }));
    await waitFor(() => {
      expect(within(exercise).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: Вес" })).toHaveValue("102,5");
    });
    await waitFor(() => {
      expect(within(exercise).queryByRole("region", { name: "Подсказка по прогрессии" })).toBeNull();
    });
  });

  it("does not show a week type for a workout outside a block", async () => {
    progression = { ...INCREASE, week_type: null };
    renderPage();
    const hint = await screen.findByRole("region", { name: "Подсказка по прогрессии" });

    expect(hint).toHaveTextContent("Повысьте вес на шаг упражнения");
    expect(hint).not.toHaveTextContent("Тип недели");
  });

  it("shows the planned exercise and keeps the screen awake", async () => {
    renderPage();
    const exercise = await screen.findByRole("region", { name: "Упражнение 1: Жим штанги лёжа" });

    expect(within(exercise).getByRole("group", { name: "Подход 1" })).toHaveTextContent("План: 8–12, RIR 2");
    expect(wakeRequest).toHaveBeenCalledWith("screen");
  });

  it("accepts a typed weight and repeats the previous session with one tap", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });
    const weight = within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: Вес" });

    expect(within(first).queryByRole("button", { name: "Жим штанги лёжа, подход 1: Вес: больше" })).toBeNull();
    await user.type(weight, "102,5");
    expect(weight).toHaveValue("102,5");
    await user.tab();
    expect(weight).toHaveValue("102,5");

    await user.click(within(first).getByRole("button", { name: "Как в прошлый раз" }));
    expect(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: Вес" })).toHaveValue("100");
    expect(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: повторы" })).toHaveValue("8");

    await waitFor(() => {
      const puts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "PUT");
      expect(puts.length).toBeGreaterThan(0);
    });
  });

  it("moves to the next field on Enter and copies the previous set", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });
    const second = screen.getByRole("group", { name: "Подход 2" });
    const weight = within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: Вес" });

    weight.focus();
    await user.keyboard("{Enter}");
    expect(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: повторы" })).toHaveFocus();

    await user.click(within(first).getByRole("button", { name: "Как в прошлый раз" }));
    await user.click(within(second).getByRole("button", { name: "Как в прошлом подходе" }));
    expect(within(second).getByRole("textbox", { name: "Жим штанги лёжа, подход 2: Вес" })).toHaveValue("100");
    expect(within(second).getByRole("textbox", { name: "Жим штанги лёжа, подход 2: повторы" })).toHaveValue("8");
  });

  it("asks before deleting a set and can undo", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });

    await user.click(within(first).getByRole("button", { name: "Удалить подход" }));
    await user.click(within(first).getByRole("button", { name: "Отмена" }));
    expect(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: Вес" })).toBeInTheDocument();

    await user.click(within(first).getByRole("button", { name: "Удалить подход" }));
    await user.click(within(first).getByRole("button", { name: "Удалить" }));
    expect(screen.queryByRole("group", { name: "Подход 2" })).toBeNull();

    await user.click(within(screen.getByRole("status", { name: "Подход удалён" })).getByRole("button", { name: "Отменить" }));
    expect(screen.getByRole("group", { name: "Подход 2" })).toBeInTheDocument();
  });

  it("keeps a set in the local queue when the network drops", async () => {
    failPuts = true;
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });

    await user.click(within(first).getByRole("button", { name: "Как в прошлый раз" }));

    await waitFor(() => {
      expect(screen.getByRole("status").textContent).toMatch(/Нет связи/);
    });
    expect(readOutbox().some((op) => op.dedupeKey === "set:s1" && (op.body as { weight: number }).weight === 100)).toBe(true);
  });

  it("shows personal records after the workout is finished", async () => {
    finishRecords = [
      {
        kind: "weight",
        exercise_id: BENCH.id,
        name: BENCH.name,
        load: 100,
        reps: 5,
        epley_1rm: null,
        unit: "kg",
      },
      {
        kind: "reps",
        exercise_id: BENCH.id,
        name: BENCH.name,
        load: 100,
        reps: 8,
        epley_1rm: null,
        unit: "kg",
      },
      {
        kind: "epley",
        exercise_id: BENCH.id,
        name: BENCH.name,
        load: 100,
        reps: 8,
        epley_1rm: 126.67,
        unit: "kg",
      },
    ];
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByText(/Рабочих подходов/)).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Личные рекорды" })).toBeNull();

    await user.click(screen.getByRole("button", { name: "Завершить" }));

    expect(await screen.findByText("Отчёт")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "День A" })).toBeInTheDocument();
    expect(screen.getByText(/1 ч/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Личные рекорды" })).toBeInTheDocument();
    expect(screen.getByText("Жим штанги лёжа: рекорд веса 100 кг")).toBeInTheDocument();
    expect(screen.getByText("Жим штанги лёжа: рекорд повторов 8 при 100 кг")).toBeInTheDocument();
    expect(screen.getByText("Жим штанги лёжа: рекорд 1ПМ 126,67 кг")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "К записи" }));
    expect(screen.getByRole("button", { name: "Отчёт" })).toBeInTheDocument();
    expect(screen.queryByText(/1 ч/)).toBeNull();
  });

  it("starts the rest timer after a working set is saved and pauses it", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });

    expect(screen.getByRole("button", { name: "Старт" })).toBeInTheDocument();
    await user.type(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: повторы" }), "8");

    // В простое табло тоже показывает 01:30, поэтому ждём статус отсчёта.
    await waitFor(() => {
      expect(screen.getByText("Отдых")).toBeInTheDocument();
    });
    expect(screen.getByRole("timer")).toHaveTextContent("01:30");

    await user.click(screen.getByRole("button", { name: "Пауза" }));
    expect(screen.getByText("На паузе")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Старт" })).toBeInTheDocument();

    const paused = screen.getByRole("timer").textContent;
    await new Promise((resolve) => setTimeout(resolve, 1100));
    expect(screen.getByRole("timer").textContent).toBe(paused);
  });

  it("does not start the rest timer for a warm-up set", async () => {
    const user = userEvent.setup();
    renderPage();
    const first = await screen.findByRole("group", { name: "Подход 1" });

    await user.click(within(first).getByRole("checkbox", { name: "Разминка" }));
    await user.type(within(first).getByRole("textbox", { name: "Жим штанги лёжа, подход 1: повторы" }), "8");

    await waitFor(() => {
      expect(readOutbox()).toHaveLength(0);
    });
    expect(vi.mocked(fetch).mock.calls.some(([, init]) => init?.method === "PUT")).toBe(true);
    expect(screen.getByText("Отдых не идёт")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Старт" })).toBeInTheDocument();
  });
});
