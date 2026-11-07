import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { formatWeekTitle, weekDates } from "../features/calendar/dates";
import { VolumePage } from "./VolumePage";

// «Сегодня» — суббота 7 ноября 2026: неделя 2–8 ноября.
const TODAY = new Date(2026, 10, 7, 12, 0, 0);
const CURRENT_WEEK = "2026-11-02";
const PREVIOUS_WEEK = "2026-10-26";

const CURRENT_RESPONSE = {
  week_start: "2026-11-02",
  week_end: "2026-11-08",
  groups: [
    { muscle: "quadriceps", sets: 22, target_min: 10, target_max: 20, status: "above" },
    { muscle: "chest", sets: 14, target_min: 10, target_max: 20, status: "in_range" },
    { muscle: "back", sets: 6, target_min: 10, target_max: 20, status: "below" },
    { muscle: null, sets: 2, target_min: null, target_max: null, status: null },
  ],
};

const EMPTY_RESPONSE = {
  week_start: "2026-10-26",
  week_end: "2026-11-01",
  groups: [],
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Ответ зависит от дня в запросе: так видно, какая неделя запрошена. */
function handleRequest(url: string): Response {
  const parsed = new URL(url, "http://localhost");
  if (parsed.pathname !== "/api/volume/muscles") {
    return jsonResponse({ detail: "Не найдено" }, 404);
  }
  const day = parsed.searchParams.get("day");
  if (day === CURRENT_WEEK) return jsonResponse(CURRENT_RESPONSE);
  if (day === PREVIOUS_WEEK) return jsonResponse(EMPTY_RESPONSE);
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/volume"]}>
        <VolumePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function requestedDays(): string[] {
  return vi
    .mocked(fetch)
    .mock.calls.map(([url]) => new URL(String(url), "http://localhost").searchParams.get("day"))
    .filter((day): day is string => day !== null);
}

describe("VolumePage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(TODAY);
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => handleRequest(url)),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows the current week with groups from the largest to the smallest", async () => {
    renderPage();

    expect(
      await screen.findByRole("heading", { name: formatWeekTitle(weekDates("2026-11-07")) }),
    ).toBeInTheDocument();
    const list = await screen.findByRole("list", { name: "Группы за неделю" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => within(row).getByRole("heading", { level: 3 }).textContent)).toEqual([
      "Квадрицепсы",
      "Грудь",
      "Спина",
      "Без группы",
    ]);
    expect(requestedDays()).toContain(CURRENT_WEEK);
  });

  it("labels each target status and states the target range", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "Группы за неделю" });
    const rows = within(list).getAllByRole("listitem");

    expect(rows[0]).toHaveTextContent("22 подхода · выше");
    expect(rows[1]).toHaveTextContent("14 подходов · в ориентире");
    expect(rows[2]).toHaveTextContent("6 подходов · ниже");
    expect(rows[0]).toHaveTextContent("Ориентир 10–20 подходов за неделю");
  });

  it("gives the no-group row no target band or status", async () => {
    renderPage();
    const list = await screen.findByRole("list", { name: "Группы за неделю" });
    const noGroup = within(list).getAllByRole("listitem")[3];

    expect(noGroup).toHaveTextContent("2 подхода");
    expect(noGroup).not.toHaveTextContent("ориентир");
    expect(noGroup).not.toHaveTextContent("ниже");
    expect(noGroup).not.toHaveTextContent("выше");
  });

  it("moves to the previous week and shows an empty state instead of zero groups", async () => {
    const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
    renderPage();
    await screen.findByRole("list", { name: "Группы за неделю" });

    await user.click(screen.getByRole("button", { name: "Предыдущая неделя" }));

    expect(
      await screen.findByText("За эту неделю рабочих подходов нет"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Группы за неделю" })).not.toBeInTheDocument();
    expect(screen.queryByText("Квадрицепсы")).not.toBeInTheDocument();
    expect(requestedDays()).toContain(PREVIOUS_WEEK);
    expect(
      screen.getByRole("heading", { name: formatWeekTitle(weekDates("2026-10-31")) }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "К текущей неделе" })).toBeInTheDocument();
  });

  it("shows an error when the volume cannot be loaded", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ detail: "Ошибка" }, 500)),
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось загрузить объём",
    );
  });
});
