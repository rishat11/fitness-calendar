import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BlocksPage } from "./BlocksPage";

const BLOCK_ID = "b1";
const PLACEMENT_ID = "p1";

const TEMPLATE_ID = "t-upper";

let workouts: { id: string; name: string }[];
let blocks: {
  id: string;
  name: string;
  length_weeks: number;
  cycle_days?: number;
  weeks?: object[];
  schedule?: object[];
}[];
let placements: {
  id: string;
  block_id: string;
  name: string;
  length_weeks: number;
  cycle_days: number;
  repeats?: boolean;
  start_date: string;
  end_date: string;
}[];
let applyStatus: number;

function jsonResponse(body: unknown, status = 200) {
  return new Response(body === undefined || status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Имитация API блоков: список, копирование, применение (с ответом 409 при занятых днях), снятие. */
function handleRequest(url: string, init?: RequestInit): Response {
  const method = init?.method ?? "GET";
  const path = new URL(url, "http://localhost").pathname;

  if (path === "/api/workouts" && method === "GET") return jsonResponse(workouts);
  if (path === "/api/blocks" && method === "GET") return jsonResponse(blocks);
  if (path === `/api/blocks/${BLOCK_ID}` && method === "PUT") {
    const body = JSON.parse(init?.body as string) as {
      name: string;
      weeks: object[];
      schedule: object[];
      cycle_days?: number;
    };
    blocks[0] = {
      ...blocks[0],
      name: body.name,
      length_weeks: body.weeks.length,
      cycle_days: body.cycle_days,
      weeks: body.weeks.map((week, index) => ({ position: index + 1, ...(week as object) })),
      schedule: body.schedule,
    };
    return jsonResponse(blocks[0]);
  }
  if (path === "/api/blocks/placements" && method === "GET") return jsonResponse(placements);
  if (path === `/api/blocks/${BLOCK_ID}/copy` && method === "POST") {
    blocks.push({ id: "b2", name: "Масса (копия)", length_weeks: 4, cycle_days: 7 });
    return jsonResponse(blocks[1], 201);
  }
  if (path === `/api/blocks/${BLOCK_ID}/apply` && method === "POST") {
    if (applyStatus !== 201) {
      return jsonResponse({ detail: "На эти даты уже есть тренировки" }, applyStatus);
    }
    return jsonResponse(placements[0], 201);
  }
  if (path === `/api/blocks/placements/${PLACEMENT_ID}` && method === "DELETE") {
    placements = [];
    return jsonResponse(undefined, 204);
  }
  return jsonResponse({ detail: "Не найдено" }, 404);
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BlocksPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function callsWith(method: string, path: string) {
  return vi
    .mocked(fetch)
    .mock.calls.filter(([url, init]) => url === path && (init?.method ?? "GET") === method);
}

describe("BlocksPage", () => {
  beforeEach(() => {
    workouts = [];
    blocks = [{ id: BLOCK_ID, name: "Масса", length_weeks: 4, cycle_days: 7 }];
    placements = [];
    applyStatus = 201;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => handleRequest(url, init)),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists blocks with their length in weeks", async () => {
    renderPage();

    const list = await screen.findByRole("list", { name: "Список блоков" });
    expect(within(list).getByText("Масса")).toBeInTheDocument();
    expect(within(list).getByText("4 цикла по 7 дней")).toBeInTheDocument();
  });

  it("copies a block through the API", async () => {
    const user = userEvent.setup();
    renderPage();
    const list = await screen.findByRole("list", { name: "Список блоков" });

    await user.click(within(list).getByRole("button", { name: "Копировать" }));

    expect(await within(list).findByText("Масса (копия)")).toBeInTheDocument();
    expect(callsWith("POST", `/api/blocks/${BLOCK_ID}/copy`)).toHaveLength(1);
  });

  it("applies a block with the chosen start date", async () => {
    const user = userEvent.setup();
    renderPage();
    const form = await screen.findByRole("form", { name: "Применить блок Масса" });

    fireEvent.change(within(form).getByLabelText("Дата старта"), {
      target: { value: "2026-11-02" },
    });
    await user.click(within(form).getByRole("button", { name: "Применить к календарю" }));

    expect(await within(form).findByRole("status")).toHaveTextContent("Блок добавлен в календарь");
    const [, init] = callsWith("POST", `/api/blocks/${BLOCK_ID}/apply`)[0];
    expect(within(form).getByRole("checkbox", { name: "Повторять без конца" })).toBeChecked();
    expect(JSON.parse(init?.body as string)).toEqual({
      start_date: "2026-11-02",
      repeats: true,
    });
  });

  it("shows the conflict message when the dates are already taken", async () => {
    applyStatus = 409;
    const user = userEvent.setup();
    renderPage();
    const form = await screen.findByRole("form", { name: "Применить блок Масса" });

    await user.click(within(form).getByRole("button", { name: "Применить к календарю" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent(
      "На эти даты уже есть тренировки",
    );
  });

  it("saves edits to an existing block", async () => {
    workouts = [{ id: TEMPLATE_ID, name: "Верх" }];
    blocks = [
      {
        id: BLOCK_ID,
        name: "Масса",
        length_weeks: 1,
        cycle_days: 7,
        weeks: [
          {
            position: 1,
            week_type: "hypertrophy",
            rep_min: 8,
            rep_max: 12,
            target_rir: 2,
            volume_multiplier: 1,
          },
        ],
        schedule: [{ day_index: 0, kind: "workout", name: "Верх", template_id: TEMPLATE_ID }],
      },
    ];
    const user = userEvent.setup();
    renderPage();
    const list = await screen.findByRole("list", { name: "Список блоков" });

    await user.click(within(list).getByRole("button", { name: "Редактировать" }));
    const form = screen.getByRole("form", { name: "Редактирование блока" });
    const name = within(form).getByLabelText("Название блока");
    expect(name).toHaveValue("Масса");
    expect(within(form).getByLabelText("День 1")).toHaveValue(TEMPLATE_ID);

    await user.clear(name);
    await user.type(name, "Сила");
    await user.click(within(form).getByRole("button", { name: "Сохранить блок" }));

    expect(await within(list).findByText("Сила")).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Редактирование блока" })).toBeNull();
    const [, init] = callsWith("PUT", `/api/blocks/${BLOCK_ID}`)[0];
    expect(JSON.parse(init?.body as string)).toMatchObject({
      name: "Сила",
      schedule: [{ day_index: 0, kind: "workout", template_id: TEMPLATE_ID }],
    });
  });

  it("sets a six-day cycle and a second deload cycle", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("list", { name: "Список блоков" });

    await user.click(screen.getByRole("button", { name: "Новый блок" }));
    const form = screen.getByRole("form", { name: "Новый блок" });
    expect(within(form).getByLabelText("Длина цикла, дней")).toHaveValue("7");
    expect(within(form).getByLabelText("День 7")).toBeInTheDocument();

    await user.selectOptions(within(form).getByLabelText("Длина цикла, дней"), "6");
    await user.selectOptions(within(form).getByLabelText("Число циклов"), "2");

    expect(within(form).queryByLabelText("День 7")).toBeNull();
    expect(within(form).getByLabelText("День 6")).toBeInTheDocument();
    expect(within(form).getByLabelText("Тип цикла 2")).toBeInTheDocument();
  });

  it("does not save a block without a schedule", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("list", { name: "Список блоков" });

    await user.click(screen.getByRole("button", { name: "Новый блок" }));
    const form = screen.getByRole("form", { name: "Новый блок" });
    await user.type(within(form).getByLabelText("Название блока"), "Пустой");
    await user.click(within(form).getByRole("button", { name: "Сохранить блок" }));

    expect(within(form).getByRole("alert")).toHaveTextContent(
      "Выберите хотя бы одну тренировку в расписании",
    );
    expect(callsWith("POST", "/api/blocks")).toHaveLength(0);
  });

  it("removes a placement from the calendar", async () => {
    placements = [
      {
        id: PLACEMENT_ID,
        block_id: BLOCK_ID,
        name: "Масса",
        length_weeks: 4,
        cycle_days: 7,
        start_date: "2026-11-02",
        end_date: "2026-11-29",
      },
    ];
    const user = userEvent.setup();
    renderPage();
    const list = await screen.findByRole("list", { name: "Применённые блоки" });
    expect(within(list).getByText("2026-11-02 — 2026-11-29 (4 цикла по 7 дней)")).toBeInTheDocument();

    await user.click(within(list).getByRole("button", { name: "Убрать из календаря" }));

    expect(callsWith("DELETE", `/api/blocks/placements/${PLACEMENT_ID}`)).toHaveLength(1);
  });
});
