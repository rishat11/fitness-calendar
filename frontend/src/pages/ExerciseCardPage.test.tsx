import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExerciseCardPage } from "./ExerciseCardPage";
import { ExercisesPage } from "./ExercisesPage";

const PROFILE = {
  goal: null,
  height_cm: null,
  age: null,
  sex: null,
  weight_unit: "kg",
  theme: "system",
};

const BENCH = {
  id: "1",
  name: "Жим штанги лёжа",
  primary_muscle: "chest",
  secondary_muscles: [],
  equipment: "barbell",
  weight_type: "standard",
  weight_unit: "kg",
  weight_step: 2.5,
  rep_min: 8,
  rep_max: 12,
  archived: false,
};

const SQUAT = {
  ...BENCH,
  id: "2",
  name: "Приседания со штангой",
  primary_muscle: "quadriceps",
};

const HISTORY = {
  sessions: [
    {
      performed_id: "perf-1",
      date: "2026-11-03",
      started_at: "2026-11-03T10:00:00Z",
      notes: ["скамья на 2"],
      sets: [
        {
          weight: 60,
          extra_weight: null,
          reps: 15,
          rir: null,
          is_warmup: true,
          is_assisted: false,
          is_negative: false,
          weight_unit: "kg",
        },
        {
          weight: 100,
          extra_weight: 2.5,
          reps: 8,
          rir: 2,
          is_warmup: false,
          is_assisted: false,
          is_negative: false,
          weight_unit: "kg",
        },
      ],
      best: { load: 102.5, reps: 8, epley_1rm: 129.83, weight_unit: "kg" },
    },
  ],
};

const HINT = {
  exercise_id: BENCH.id,
  status: "increase_weight",
  message: "Повысьте вес на шаг упражнения. После повышения ожидаются повторы около нижней границы.",
  suggested_weight: 102.5,
  weight_unit: "kg",
  last_session_id: "perf-1",
  epley_1rm: 140,
  week_type: "high_reps",
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function handleRequest(url: string): Response {
  const parsed = new URL(url, "http://localhost");
  const path = parsed.pathname;
  if (path === "/api/profile") return jsonResponse(PROFILE);
  if (path === "/api/exercises") return jsonResponse([BENCH, SQUAT]);
  const history = path.match(/^\/api\/exercises\/([^/]+)\/history$/);
  if (history) return jsonResponse(history[1] === BENCH.id ? HISTORY : { sessions: [] });
  const exercise = path.match(/^\/api\/exercises\/([^/]+)$/);
  if (exercise) {
    const found = [BENCH, SQUAT].find((item) => item.id === exercise[1]);
    return found ? jsonResponse(found) : jsonResponse({ detail: "Упражнение не найдено" }, 404);
  }
  if (path.startsWith("/api/progression/")) {
    return jsonResponse(path.endsWith(`/${BENCH.id}`) ? HINT : null);
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/exercises"]}>
        <Routes>
          <Route path="/exercises" element={<ExercisesPage />} />
          <Route path="/exercises/:exerciseId" element={<ExerciseCardPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ExerciseCardPage", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => handleRequest(url)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("opens the card from the list and shows the past result, note and hint", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(await screen.findByRole("link", { name: "Жим штанги лёжа" }));

    expect(await screen.findByRole("heading", { name: "Жим штанги лёжа" })).toBeInTheDocument();
    expect(screen.getByText("Грудь · Штанга")).toBeInTheDocument();
    expect(screen.getByText(/Повторы 8–12/)).toBeInTheDocument();
    expect(screen.getByText("скамья на 2")).toBeInTheDocument();
    expect(screen.getByText("100 кг, доп. 2,5 кг, 8 повт., RIR 2")).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Подсказка по прогрессии" })).toHaveTextContent(
      "Повысьте вес на шаг упражнения",
    );
    expect(screen.getByRole("region", { name: "Подсказка по прогрессии" })).toHaveTextContent(
      "Тип недели: Высокие повторы",
    );
    expect(screen.getByRole("img", { name: /График прогрессии/ })).toBeInTheDocument();
    expect(screen.getByText("Расчётный 1ПМ по формуле Эпли. Это не цель.")).toBeInTheDocument();
  });

  it("shows an empty history without crashing", async () => {
    const user = userEvent.setup();
    renderList();

    await user.click(await screen.findByRole("link", { name: "Приседания со штангой" }));

    expect(
      await screen.findByRole("heading", { name: "Приседания со штангой" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Истории пока нет/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /График прогрессии/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Подсказка по прогрессии" })).not.toBeInTheDocument();
  });
});
