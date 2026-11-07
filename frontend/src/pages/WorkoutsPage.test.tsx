import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { WorkoutsPage } from "./WorkoutsPage";

type StoredWorkout = {
  id: string;
  name: string;
  items: { id: string }[];
};

let store: StoredWorkout[];
let nextId: number;

function jsonResponse(body: unknown, status = 200) {
  return new Response(body === undefined ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Имитация API раздела «Тренировки»: список, создание, переименование, копирование, удаление. */
function handleRequest(url: string, init?: RequestInit): Response {
  const method = init?.method ?? "GET";
  const parsed = new URL(url, "http://localhost");
  const path = parsed.pathname;

  if (path === "/api/workouts" && method === "GET") {
    return jsonResponse(store);
  }
  if (path === "/api/workouts" && method === "POST") {
    const body = JSON.parse(init?.body as string);
    const created = { id: String(nextId++), name: body.name, items: [] };
    store.push(created);
    return jsonResponse(created, 201);
  }
  const copyMatch = path.match(/^\/api\/workouts\/(\d+)\/copy$/);
  if (copyMatch && method === "POST") {
    const source = store.find((item) => item.id === copyMatch[1]);
    const copy = { id: String(nextId++), name: `${source?.name} (копия)`, items: [] };
    store.push(copy);
    return jsonResponse(copy, 201);
  }
  const idMatch = path.match(/^\/api\/workouts\/(\d+)$/);
  if (idMatch && method === "PATCH") {
    const target = store.find((item) => item.id === idMatch[1]);
    if (target) target.name = JSON.parse(init?.body as string).name;
    return jsonResponse(target);
  }
  if (idMatch && method === "DELETE") {
    store = store.filter((item) => item.id !== idMatch[1]);
    return jsonResponse(undefined, 204);
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function OpenedWorkout() {
  const location = useLocation();
  const editing = (location.state as { editing?: boolean } | null)?.editing;
  return <p>{editing ? "Редактор открыт для правки" : "Редактор открыт"}</p>;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/workouts"]}>
        <Routes>
          <Route path="/workouts" element={<WorkoutsPage />} />
          <Route path="/workouts/:workoutId" element={<OpenedWorkout />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function postCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
}

describe("WorkoutsPage", () => {
  beforeEach(() => {
    store = [
      { id: "1", name: "День A", items: [{ id: "a" }, { id: "b" }] },
      { id: "2", name: "День B", items: [] },
    ];
    nextId = 3;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists workouts with their exercise counts", async () => {
    renderPage();

    const list = await screen.findByRole("list", { name: "Список тренировок" });
    const rowA = within(list).getByText("День A").closest("li") as HTMLElement;
    expect(within(rowA).getByText("2 упражнения")).toBeInTheDocument();
    const rowB = within(list).getByText("День B").closest("li") as HTMLElement;
    expect(within(rowB).getByText("0 упражнений")).toBeInTheDocument();
  });

  it("creates an empty workout and opens its editor", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("День A");

    const form = screen.getByRole("form", { name: "Новая тренировка" });
    await user.type(within(form).getByLabelText("Название тренировки"), "День C");
    await user.click(within(form).getByRole("button", { name: "Создать" }));

    expect(await screen.findByText("Редактор открыт для правки")).toBeInTheDocument();
    expect(JSON.parse(postCalls()[0][1]?.body as string)).toEqual({ name: "День C", items: [] });
  });

  it("does not create a workout without a name", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("День A");

    await user.click(screen.getByRole("button", { name: "Создать" }));

    expect(screen.getByRole("alert")).toHaveTextContent("Укажите название");
    expect(postCalls()).toHaveLength(0);
  });

  it("renames a workout inline", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText("День B")).closest("li") as HTMLElement;

    await user.click(within(row).getByRole("button", { name: "Переименовать" }));
    const rename = within(row).getByRole("form", { name: "Переименование тренировки" });
    const input = within(rename).getByLabelText("Новое название");
    await user.clear(input);
    await user.type(input, "День Б");
    await user.click(within(rename).getByRole("button", { name: "Сохранить" }));

    expect(await screen.findByText("День Б")).toBeInTheDocument();
    expect(screen.queryByText("День B")).not.toBeInTheDocument();
  });

  it("copies a workout next to the original", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText("День A")).closest("li") as HTMLElement;

    await user.click(within(row).getByRole("button", { name: "Копировать" }));

    expect(await screen.findByText("День A (копия)")).toBeInTheDocument();
    expect(screen.getByText("День A")).toBeInTheDocument();
  });

  it("deletes only after confirmation", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText("День B")).closest("li") as HTMLElement;

    await user.click(within(row).getByRole("button", { name: "Удалить" }));
    expect(within(row).getByText("Удалить тренировку?")).toBeInTheDocument();
    await user.click(within(row).getByRole("button", { name: "Отмена" }));
    expect(screen.getByText("День B")).toBeInTheDocument();

    await user.click(within(row).getByRole("button", { name: "Удалить" }));
    await user.click(within(row).getByRole("button", { name: "Удалить" }));

    await waitFor(() => {
      expect(screen.queryByText("День B")).not.toBeInTheDocument();
    });
  });
});
