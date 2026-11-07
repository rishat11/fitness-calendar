import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { type TodayEntry } from "../api/client";
import { TodayPage } from "./TodayPage";

const USER = { id: "u1", email: "a@example.com", created_at: "2026-01-01T00:00:00Z" };

function workout(overrides: Partial<TodayEntry> = {}): TodayEntry {
  return {
    id: "plan-1",
    date: "2026-11-07",
    kind: "workout",
    status: "planned",
    is_fixed: false,
    position: 0,
    template_id: null,
    name: "День A",
    log_state: "none",
    items: [
      {
        position: 0,
        exercise: {
          exercise_id: "ex-1",
          name: "Жим штанги лёжа",
          primary_muscle: "chest",
          equipment: "barbell",
          weight_type: "standard",
          weight_unit: "kg",
          weight_step: 2.5,
        },
        sets: [
          { rep_min: 8, rep_max: 12, target_rir: 2, rest_seconds: 90 },
          { rep_min: 8, rep_max: 12, target_rir: 2, rest_seconds: 90 },
        ],
      },
    ],
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderToday() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <TodayPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const CONTINUE = {
  exercise_id: "ex-1",
  status: "continue",
  message: "Продолжайте, добавляйте повторы.",
  suggested_weight: null,
  weight_unit: "kg",
  last_session_id: "perf-old",
  epley_1rm: 133.33,
};

describe("TodayPage", () => {
  let entries: TodayEntry[];
  let exportReminder = false;
  let progression: unknown = null;

  beforeEach(() => {
    entries = [workout()];
    exportReminder = false;
    progression = null;
    localStorage.clear();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        const path = new URL(url, "http://localhost").pathname;
        if (path === "/api/auth/me") return jsonResponse(USER);
        if (path === "/api/today") {
          return jsonResponse({ date: "2026-11-07", entries, export_reminder: exportReminder });
        }
        if (path === "/api/plan") return jsonResponse(entries);
        if (path === "/api/plan/shift/history") return jsonResponse([]);
        if (path.startsWith("/api/progression/")) return jsonResponse(progression);
        return jsonResponse({ detail: "Не найдено" }, 404);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows a progression hint for an exercise in today's workout", async () => {
    progression = CONTINUE;
    renderToday();

    expect(await screen.findByRole("heading", { name: "День A" })).toBeInTheDocument();
    expect(await screen.findByRole("region", { name: "Подсказка по прогрессии" })).toHaveTextContent(
      "Продолжайте, добавляйте повторы.",
    );
  });

  it("opens today's planned workout", async () => {
    renderToday();

    expect(await screen.findByRole("heading", { name: "День A" })).toBeInTheDocument();
    expect(screen.getByText("Жим штанги лёжа")).toBeInTheDocument();
    expect(screen.getByText("Запланирована")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть" })).toHaveAttribute("href", "/log/plan-1");
    expect(screen.queryByText(/БЖУ/)).not.toBeInTheDocument();
    expect(screen.queryByText(/вес/i)).not.toBeInTheDocument();
  });

  it("continues a workout that is already started", async () => {
    entries = [workout({ log_state: "open" })];
    renderToday();

    expect(await screen.findByRole("link", { name: "Продолжить" })).toHaveAttribute("href", "/log/plan-1");
  });

  it("shows a rest day without a workout link", async () => {
    entries = [
      workout({
        id: "rest-1",
        kind: "rest",
        status: null,
        name: null,
        items: [],
        log_state: "none",
      }),
    ];
    renderToday();

    expect(await screen.findByRole("heading", { name: "День отдыха" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Открыть" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Продолжить" })).not.toBeInTheDocument();
  });

  it("offers the calendar when the day is empty", async () => {
    entries = [];
    renderToday();

    expect(await screen.findByText("На сегодня ничего не запланировано.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть календарь" })).toHaveAttribute("href", "/calendar");
    expect(screen.getByRole("button", { name: "Сдвинуть план" })).toBeDisabled();
    expect(screen.queryByText(/БЖУ/)).not.toBeInTheDocument();
  });

  it("opens the shift menu for today's workout", async () => {
    const user = userEvent.setup();
    renderToday();

    await user.click(await screen.findByRole("button", { name: "Сдвинуть план" }));

    expect(screen.getByRole("region", { name: "Сдвиг плана" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Эта и следующие" })).toBeEnabled();
  });

  it("reminds to export and hides the reminder for this account", async () => {
    exportReminder = true;
    const user = userEvent.setup();
    renderToday();

    expect(await screen.findByRole("status", { name: "Резервная копия" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Открыть настройки" })).toHaveAttribute("href", "/settings");

    await user.click(screen.getByRole("button", { name: "Не сейчас" }));

    expect(screen.queryByRole("status", { name: "Резервная копия" })).not.toBeInTheDocument();
    expect(localStorage.getItem("fitness-calendar.export-reminder-hidden-until.u1")).toBeTruthy();
  });
});
