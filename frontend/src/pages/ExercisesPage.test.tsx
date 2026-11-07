import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ExercisesPage } from "./ExercisesPage";

type StoredExercise = {
  id: string;
  name: string;
  primary_muscle: string;
  secondary_muscles: string[];
  equipment: string;
  weight_type: string;
  weight_unit: string;
  weight_step: number;
  rep_min: number;
  rep_max: number;
};

const PROFILE = {
  goal: null,
  height_cm: null,
  age: null,
  sex: null,
  weight_unit: "kg",
  theme: "system",
};

function exercise(overrides: Partial<StoredExercise>): StoredExercise {
  return {
    id: "0",
    name: "Упражнение",
    primary_muscle: "chest",
    secondary_muscles: [],
    equipment: "barbell",
    weight_type: "standard",
    weight_unit: "kg",
    weight_step: 2.5,
    rep_min: 8,
    rep_max: 12,
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

let store: StoredExercise[];
let nextId: number;

/** Имитация API: список с поиском, создание и удаление. */
function handleRequest(url: string, init?: RequestInit): Response {
  const method = init?.method ?? "GET";
  const parsed = new URL(url, "http://localhost");

  if (parsed.pathname === "/api/profile") {
    return jsonResponse(PROFILE);
  }
  if (parsed.pathname === "/api/exercises" && method === "GET") {
    const q = (parsed.searchParams.get("q") ?? "").toLowerCase();
    return jsonResponse(store.filter((item) => item.name.toLowerCase().includes(q)));
  }
  if (parsed.pathname === "/api/exercises" && method === "POST") {
    const created = { ...JSON.parse(init?.body as string), id: String(nextId++) };
    store.push(created);
    return jsonResponse(created, 201);
  }
  const deleteMatch = parsed.pathname.match(/^\/api\/exercises\/(\d+)$/);
  if (deleteMatch && method === "DELETE") {
    if (deleteMatch[1] === "1") {
      return jsonResponse(
        { detail: "Упражнение входит в тренировки. Сначала уберите его оттуда." },
        409,
      );
    }
    store = store.filter((item) => item.id !== deleteMatch[1]);
    return new Response(null, { status: 204 });
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/exercises"]}>
        <ExercisesPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function postCalls() {
  return vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "POST");
}

describe("ExercisesPage", () => {
  beforeEach(() => {
    store = [
      exercise({ id: "1", name: "Жим штанги лёжа", primary_muscle: "chest" }),
      exercise({ id: "2", name: "Приседания со штангой", primary_muscle: "quadriceps" }),
      exercise({ id: "3", name: "Тяга блока", primary_muscle: "back", equipment: "cable" }),
    ];
    nextId = 4;
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists exercises without an archive control", async () => {
    renderPage();

    expect(await screen.findByText("Жим штанги лёжа")).toBeInTheDocument();
    expect(screen.getByText("Приседания со штангой")).toBeInTheDocument();
    expect(screen.getByText("Тяга блока")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "В архив" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Показать архив")).not.toBeInTheDocument();
  });

  it("filters the list by name", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Жим штанги лёжа");

    await user.type(screen.getByLabelText("Поиск по названию"), "присед");

    await waitFor(() => {
      expect(screen.queryByText("Жим штанги лёжа")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Приседания со штангой")).toBeInTheDocument();
  });

  it("quick create sends default step and reps for the chosen group", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Жим штанги лёжа");
    const quick = screen.getByRole("form", { name: "Быстрое создание упражнения" });

    await user.type(within(quick).getByLabelText("Название"), "Жим гантелей сидя");
    await user.selectOptions(within(quick).getByLabelText("Основная группа"), "shoulders");
    await user.click(within(quick).getByRole("button", { name: "Добавить" }));

    expect(await screen.findByText("Жим гантелей сидя")).toBeInTheDocument();
    expect(postCalls()).toHaveLength(1);
    expect(JSON.parse(postCalls()[0][1]?.body as string)).toEqual({
      name: "Жим гантелей сидя",
      primary_muscle: "shoulders",
      secondary_muscles: [],
      equipment: "barbell",
      weight_type: "standard",
      weight_unit: "kg",
      weight_step: 2.5,
      rep_min: 8,
      rep_max: 12,
    });
  });

  it("quick create asks for a group before sending", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Жим штанги лёжа");
    const quick = screen.getByRole("form", { name: "Быстрое создание упражнения" });

    await user.type(within(quick).getByLabelText("Название"), "Хак-присед");
    await user.click(within(quick).getByRole("button", { name: "Добавить" }));

    expect(within(quick).getByRole("alert")).toHaveTextContent("Выберите основную группу");
    expect(postCalls()).toHaveLength(0);
  });

  it("full form rejects a reversed rep range without sending a request", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByText("Жим штанги лёжа");

    await user.click(screen.getByRole("button", { name: "Создать подробно" }));
    const form = screen.getByRole("form", { name: "Новое упражнение" });
    await user.type(within(form).getByLabelText("Название"), "Тяга гантели");
    await user.selectOptions(within(form).getByLabelText("Основная группа"), "back");
    await user.clear(within(form).getByLabelText(/Повторы, от/));
    await user.type(within(form).getByLabelText(/Повторы, от/), "15");
    await user.click(within(form).getByRole("button", { name: "Сохранить" }));

    expect(
      within(form).getByText("Повторы от 1 до 100, нижняя граница не больше верхней"),
    ).toBeInTheDocument();
    expect(postCalls()).toHaveLength(0);
  });

  it("refuses to delete an exercise that is still in a workout", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText("Жим штанги лёжа")).closest("li");
    expect(row).not.toBeNull();

    await user.click(within(row as HTMLElement).getByRole("button", { name: "Удалить" }));
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Удалить" }));

    expect(
      await within(row as HTMLElement).findByRole("alert"),
    ).toHaveTextContent("Упражнение входит в тренировки. Сначала уберите его оттуда.");
    expect(screen.getByText("Жим штанги лёжа")).toBeInTheDocument();
  });

  it("deletes an exercise that is not used", async () => {
    const user = userEvent.setup();
    renderPage();
    const row = (await screen.findByText("Приседания со штангой")).closest("li");
    expect(row).not.toBeNull();

    await user.click(within(row as HTMLElement).getByRole("button", { name: "Удалить" }));
    await user.click(within(row as HTMLElement).getByRole("button", { name: "Удалить" }));

    await waitFor(() => {
      expect(screen.queryByText("Приседания со штангой")).not.toBeInTheDocument();
    });
    expect(screen.getByText("Жим штанги лёжа")).toBeInTheDocument();
  });
});
