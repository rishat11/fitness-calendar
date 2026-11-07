import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { addDays } from "../features/calendar/dates";
import { CalendarPage } from "./CalendarPage";

type StoredEntry = {
  id: string;
  date: string;
  kind: "workout" | "rest";
  status: "planned" | "done" | "skipped" | "moved";
  is_fixed: boolean;
  position: number;
  template_id: string | null;
  name: string | null;
  items: { position: number; exercise: { name: string }; sets: { rep_min: number }[] }[];
};

let entries: StoredEntry[];
let nextId: number;
let shiftHistory: {
  id: string;
  created_at: string;
  operation: string;
  change_count: number;
  undo: { id: string; date: string; status: StoredEntry["status"] };
}[];
const workouts = [{ id: "w1", name: "День A", items: [] }];

function jsonResponse(body: unknown, status = 200) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function makeEntry(partial: Partial<StoredEntry> & Pick<StoredEntry, "date">): StoredEntry {
  return {
    id: String(nextId++),
    kind: "workout",
    status: "planned",
    is_fixed: false,
    position: entries.filter((entry) => entry.date === partial.date).length,
    template_id: null,
    name: "Тренировка",
    items: [],
    ...partial,
  };
}

/** Имитация API плана и библиотеки тренировок в памяти. */
function handleRequest(url: string, init?: RequestInit): Response {
  const method = init?.method ?? "GET";
  const parsed = new URL(url, "http://localhost");
  const path = parsed.pathname;
  const body = init?.body ? JSON.parse(init.body as string) : undefined;

  if (path === "/api/workouts" && method === "GET") {
    return jsonResponse(workouts);
  }
  if (path === "/api/plan" && method === "GET") {
    const start = parsed.searchParams.get("start") ?? "";
    const end = parsed.searchParams.get("end") ?? "";
    return jsonResponse(
      entries
        .filter((entry) => entry.date >= start && entry.date <= end)
        .sort((a, b) => a.date.localeCompare(b.date) || a.position - b.position),
    );
  }
  if (path === "/api/plan/entries" && method === "POST") {
    if (body.kind === "rest" && entries.some((entry) => entry.date === body.date)) {
      return jsonResponse({ detail: "На этот день уже что-то запланировано" }, 409);
    }
    const hasRest = entries.some((entry) => entry.date === body.date && entry.kind === "rest");
    if (body.kind !== "rest" && hasRest) {
      return jsonResponse({ detail: "Этот день отмечен как отдых" }, 409);
    }
    const created = makeEntry({
      date: body.date,
      kind: body.kind ?? "workout",
      name: body.kind === "rest" ? null : body.name ?? "День A",
      template_id: body.template_id ?? null,
    });
    entries.push(created);
    return jsonResponse(created, 201);
  }
  if (path === "/api/plan/shift/history" && method === "GET") {
    return jsonResponse(
      shiftHistory.map((item) => ({
        id: item.id,
        created_at: item.created_at,
        operation: item.operation,
        change_count: item.change_count,
      })),
    );
  }
  if (
    (path === "/api/plan/shift/preview" || path === "/api/plan/shift/apply") &&
    method === "POST"
  ) {
    const target = entries.find((entry) => entry.id === body.entry_id);
    if (!target) return jsonResponse({ detail: "Запись плана не найдена" }, 404);
    const days = typeof body.days === "number" ? body.days : 0;
    let dateAfter = body.operation === "skip" ? target.date : addDays(target.date, days);
    const landedOnRest = entries.some(
      (entry) => entry.kind === "rest" && entry.date === addDays(target.date, days),
    );
    if (landedOnRest && body.resolution === "cascade") dateAfter = addDays(dateAfter, 1);
    const conflict = body.operation !== "skip" && landedOnRest && body.resolution !== "cascade";
    const preview = {
      changes: [
        {
          id: target.id,
          name: target.name,
          kind: target.kind,
          date_before: target.date,
          date_after: dateAfter,
          status_before: target.status,
          status_after: body.operation === "skip" ? "skipped" : target.status,
        },
      ],
      conflicts: conflict
        ? [
            {
              entry_id: target.id,
              date: addDays(target.date, days),
              reason: "blocked",
              message: "Этот день нельзя совместить с переносимой записью",
            },
          ]
        : [],
      resolutions: conflict ? ["cascade", "cancel"] : [],
    };
    if (path.endsWith("/preview")) return jsonResponse(preview);
    if (preview.conflicts.length > 0) {
      return jsonResponse({ detail: "Сдвиг затрагивает занятый день" }, 409);
    }
    target.date = preview.changes[0].date_after;
    target.status = preview.changes[0].status_after;
    shiftHistory.unshift({
      id: `log-${shiftHistory.length + 1}`,
      created_at: "2026-11-07T12:00:00Z",
      operation: body.operation,
      change_count: 1,
      undo: { id: target.id, date: preview.changes[0].date_before, status: preview.changes[0].status_before },
    });
    return jsonResponse({ applied: true, changes: preview.changes, log_id: shiftHistory[0].id });
  }
  if (path === "/api/plan/shift/undo" && method === "POST") {
    const last = shiftHistory.shift();
    if (!last) return jsonResponse({ detail: "Нет операции для отмены" }, 404);
    const target = entries.find((entry) => entry.id === last.undo.id);
    if (!target) return jsonResponse({ detail: "Запись плана не найдена" }, 404);
    const change = {
      id: target.id,
      name: target.name,
      kind: target.kind,
      date_before: target.date,
      date_after: last.undo.date,
      status_before: target.status,
      status_after: last.undo.status,
    };
    target.date = last.undo.date;
    target.status = last.undo.status;
    return jsonResponse({ applied: true, changes: [change], log_id: last.id });
  }
  if (path === "/api/plan/cycles" && method === "POST") {
    const created = [0, 1].map((offset) =>
      makeEntry({ date: offset === 0 ? body.start_date : "2026-11-04", name: "День A" }),
    );
    entries.push(...created);
    return jsonResponse(created, 201);
  }
  const idMatch = path.match(/^\/api\/plan\/(\d+)$/);
  if (idMatch && method === "PATCH") {
    const target = entries.find((entry) => entry.id === idMatch[1]);
    if (!target) return jsonResponse({ detail: "Запись плана не найдена" }, 404);
    // Как на сервере: тренировку нельзя перенести на день, где уже отдых.
    const restOnTarget = entries.some(
      (entry) => entry.id !== target.id && entry.date === body.date && entry.kind === "rest",
    );
    if (body.date !== undefined && restOnTarget && target.kind !== "rest") {
      return jsonResponse({ detail: "Этот день отмечен как отдых" }, 409);
    }
    if (body.date !== undefined) target.date = body.date;
    if (body.status !== undefined) target.status = body.status;
    if (body.is_fixed !== undefined) target.is_fixed = body.is_fixed;
    return jsonResponse(target);
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CalendarPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function cell(iso: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(`[data-date="${iso}"]`);
  if (!element) throw new Error(`no cell for ${iso}`);
  return element;
}

function dayButton(iso: string) {
  return within(cell(iso)).getByRole("button", { name: /^Выбрать день/ });
}

function postBodies(path: string) {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([url, init]) => String(url).startsWith(path) && init?.method === "POST")
    .map(([, init]) => JSON.parse(init?.body as string));
}

describe("CalendarPage", () => {
  beforeEach(() => {
    // Сегодня — пятница 6 ноября 2026: месяц и неделя предсказуемы.
    vi.useFakeTimers({ shouldAdvanceTime: true, toFake: ["Date"] });
    vi.setSystemTime(new Date(2026, 10, 6, 12, 0, 0));
    nextId = 1;
    entries = [];
    shiftHistory = [];
    entries.push(makeEntry({ date: "2026-11-10", name: "День A", items: [] }));
    entries.push(makeEntry({ date: "2026-11-12", kind: "rest", name: null }));
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)));
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("shows plan entries in their day cells", async () => {
    renderPage();

    expect(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ })).toBeInTheDocument();
    expect(within(cell("2026-11-12")).getByRole("button", { name: /Отдых/ })).toBeInTheDocument();
    expect(within(cell("2026-11-11")).queryByRole("button", { name: /День A|Отдых/ })).toBeNull();
  });

  it("adds a rest day to the selected date", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: /День A/ });

    await user.click(dayButton("2026-11-14"));
    await user.click(screen.getByRole("button", { name: "Отметить отдых" }));

    expect(await within(cell("2026-11-14")).findByRole("button", { name: /Отдых/ })).toBeInTheDocument();
    expect(postBodies("/api/plan/entries")).toEqual([{ date: "2026-11-14", kind: "rest" }]);
  });

  it("explains why a workout cannot be put on a rest day", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: /Отдых/ });

    await user.click(dayButton("2026-11-12"));
    await user.selectOptions(screen.getByLabelText("Тренировка из библиотеки"), "w1");
    await user.click(screen.getByRole("button", { name: "Поставить на день" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Этот день отмечен как отдых");
  });

  it("changes the status of a planned workout from its panel", async () => {
    const user = userEvent.setup();
    renderPage();
    const card = await within(cell("2026-11-10")).findByRole("button", { name: /День A/ });

    await user.click(card);
    const panel = screen.getByRole("region", { name: "Запись: День A" });
    await user.click(within(panel).getByRole("button", { name: "Выполнена" }));

    await waitFor(() => {
      expect(within(cell("2026-11-10")).getByRole("button", { name: /Выполнена/ })).toBeInTheDocument();
    });
    const patches = vi
      .mocked(fetch)
      .mock.calls.filter(([, init]) => init?.method === "PATCH")
      .map(([, init]) => init?.body);
    expect(patches).toEqual([JSON.stringify({ status: "done" })]);
  });

  it("blocks status changes that the server would refuse", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    await user.click(within(panel).getByRole("button", { name: "Выполнена" }));
    await waitFor(() => {
      expect(within(panel).getByRole("button", { name: "Пропущена" })).toBeDisabled();
    });
    expect(within(panel).getByRole("button", { name: "Запланирована" })).toBeEnabled();
  });

  it("moves a planned workout to a chosen date", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    fireEvent.change(within(panel).getByLabelText("Новая дата"), { target: { value: "2026-11-15" } });
    await user.click(within(panel).getByRole("button", { name: "Перенести" }));

    expect(await within(cell("2026-11-15")).findByRole("button", { name: /День A/ })).toBeInTheDocument();
    expect(within(cell("2026-11-10")).queryByRole("button", { name: /День A/ })).toBeNull();
  });

  it("shows the conflict and keeps the workout in place when moved onto a rest day", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    fireEvent.change(within(panel).getByLabelText("Новая дата"), { target: { value: "2026-11-12" } });
    await user.click(within(panel).getByRole("button", { name: "Перенести" }));

    expect(await within(panel).findByRole("alert")).toHaveTextContent("Этот день отмечен как отдых");
    expect(within(cell("2026-11-10")).getByRole("button", { name: /День A/ })).toBeInTheDocument();
    expect(within(cell("2026-11-12")).getByRole("button", { name: /Отдых/ })).toBeInTheDocument();
  });

  it("keeps the panel open when the entry is moved to a month outside the view", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    fireEvent.change(within(panel).getByLabelText("Новая дата"), { target: { value: "2026-12-03" } });
    await user.click(within(panel).getByRole("button", { name: "Перенести" }));

    await waitFor(() => {
      expect(within(cell("2026-11-10")).queryByRole("button", { name: /День A/ })).toBeNull();
    });
    expect(screen.getByRole("region", { name: "Запись: День A" })).toBeInTheDocument();
  });

  it("does not allow moving a completed workout", async () => {
    entries[0].status = "done";
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    fireEvent.change(within(panel).getByLabelText("Новая дата"), { target: { value: "2026-11-15" } });

    expect(within(panel).getByRole("button", { name: "Перенести" })).toBeDisabled();
  });

  it("creates a weekly cycle from the library workout", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: /День A/ });

    fireEvent.change(screen.getByLabelText("Дата записи"), { target: { value: "2026-11-02" } });
    await user.selectOptions(screen.getByLabelText("Тренировка из библиотеки"), "w1");
    await user.click(screen.getByLabelText("Пн"));
    await user.click(screen.getByLabelText("Ср"));
    await user.clear(screen.getByLabelText("Количество недель"));
    await user.type(screen.getByLabelText("Количество недель"), "1");
    await user.click(screen.getByRole("button", { name: "Создать цикл" }));

    expect(await screen.findByText("Создано тренировок: 2")).toBeInTheDocument();
    expect(postBodies("/api/plan/cycles")).toEqual([
      { template_id: "w1", start_date: "2026-11-02", weekdays: [0, 2], weeks: 1 },
    ]);
  });

  it("previews a shift, applies it, and undoes it from the toast", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    await user.click(within(panel).getByRole("button", { name: "Эта и следующие" }));
    const dialog = await screen.findByRole("dialog", { name: "Предпросмотр сдвига" });
    expect(within(dialog).getByRole("list", { name: "Было и станет" })).toHaveTextContent("День A");
    await user.click(within(dialog).getByRole("button", { name: "Применить" }));

    expect(await within(cell("2026-11-11")).findByRole("button", { name: /День A/ })).toBeInTheDocument();
    const toast = await screen.findByRole("status", { name: "План изменён" });
    expect(toast).toHaveTextContent("План изменён");
    await user.click(within(toast).getByRole("button", { name: "Отменить" }));

    expect(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ })).toBeInTheDocument();
    expect(postBodies("/api/plan/shift/apply")).toEqual([
      { operation: "shift_following", entry_id: "1", days: 1 },
    ]);
  });

  it("shows conflict choices and steps the chain over a rest day", async () => {
    const user = userEvent.setup();
    renderPage();
    await user.click(await within(cell("2026-11-10")).findByRole("button", { name: /День A/ }));
    const panel = screen.getByRole("region", { name: "Запись: День A" });

    fireEvent.change(within(panel).getByLabelText("На сколько дней"), { target: { value: "2" } });
    await user.click(within(panel).getByRole("button", { name: "Только эта" }));

    const dialog = await screen.findByRole("dialog", { name: "Предпросмотр сдвига" });
    expect(within(dialog).getByRole("alert")).toHaveTextContent("нельзя совместить");
    expect(within(dialog).queryByRole("button", { name: "Оставить две в один день" })).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Сдвинуть цепочку дальше" }));
    await user.click(await within(dialog).findByRole("button", { name: "Применить" }));

    expect(await within(cell("2026-11-13")).findByRole("button", { name: /День A/ })).toBeInTheDocument();
    expect(postBodies("/api/plan/shift/apply")).toEqual([
      { operation: "shift_only", entry_id: "1", days: 2, resolution: "cascade" },
    ]);
  });

  it("keeps the cycle button disabled until days and library workout are chosen", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("button", { name: /День A/ });

    const button = screen.getByRole("button", { name: "Создать цикл" });
    expect(button).toBeDisabled();
    await user.selectOptions(screen.getByLabelText("Тренировка из библиотеки"), "w1");
    expect(button).toBeDisabled();
    await user.click(screen.getByLabelText("Пн"));
    expect(button).toBeEnabled();
  });
});
