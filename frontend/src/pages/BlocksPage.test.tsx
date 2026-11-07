import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { BlocksPage } from "./BlocksPage";

const BLOCK_ID = "b1";
const PLACEMENT_ID = "p1";

let blocks: { id: string; name: string; length_weeks: number }[];
let placements: { id: string; block_id: string; name: string; length_weeks: number; start_date: string; end_date: string }[];
let applyStatus: number;
let suggestion: {
  suggest: boolean;
  placement_id: string;
  week_position: number | null;
  message: string;
  reasons: { code: string; text: string }[];
};

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

  if (path === "/api/workouts" && method === "GET") return jsonResponse([]);
  if (path === "/api/blocks" && method === "GET") return jsonResponse(blocks);
  if (path === "/api/blocks/placements" && method === "GET") return jsonResponse(placements);
  if (path === `/api/blocks/${BLOCK_ID}/copy` && method === "POST") {
    blocks.push({ id: "b2", name: "Масса (копия)", length_weeks: 4 });
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
  if (path === `/api/blocks/placements/${PLACEMENT_ID}/deload-suggestion` && method === "GET") {
    return jsonResponse(suggestion);
  }
  if (
    path === `/api/blocks/placements/${PLACEMENT_ID}/deload-suggestion/accept` &&
    method === "POST"
  ) {
    suggestion = { ...suggestion, suggest: false, reasons: [] };
    return jsonResponse({
      placement_id: PLACEMENT_ID,
      week_position: 2,
      volume_multiplier: 0.5,
      target_rir: 4,
    });
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
    blocks = [{ id: BLOCK_ID, name: "Масса", length_weeks: 4 }];
    placements = [];
    applyStatus = 201;
    suggestion = {
      suggest: false,
      placement_id: PLACEMENT_ID,
      week_position: null,
      message: "Признаков усталости пока недостаточно, чтобы разгрузиться раньше плана.",
      reasons: [],
    };
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
    expect(within(list).getByText("4 недели")).toBeInTheDocument();
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
    expect(JSON.parse(init?.body as string)).toEqual({ start_date: "2026-11-02" });
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
        start_date: "2026-11-02",
        end_date: "2026-11-29",
      },
    ];
    const user = userEvent.setup();
    renderPage();
    const list = await screen.findByRole("list", { name: "Применённые блоки" });
    expect(within(list).getByText("2026-11-02 — 2026-11-29 (4 недели)")).toBeInTheDocument();

    await user.click(within(list).getByRole("button", { name: "Убрать из календаря" }));

    expect(callsWith("DELETE", `/api/blocks/placements/${PLACEMENT_ID}`)).toHaveLength(1);
  });

  it("shows the guide and accepts an early deload", async () => {
    placements = [
      {
        id: PLACEMENT_ID,
        block_id: BLOCK_ID,
        name: "Масса",
        length_weeks: 4,
        start_date: "2026-11-02",
        end_date: "2026-11-29",
      },
    ];
    suggestion = {
      suggest: true,
      placement_id: PLACEMENT_ID,
      week_position: 2,
      message: "Есть признаки усталости. Эту неделю можно сделать разгрузкой раньше плана.",
      reasons: [
        {
          code: "low_rir",
          text: "В последней тренировочной неделе RIR 0–1 у двух и более упражнений.",
        },
      ],
    };
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("region", { name: "Справка" })).toBeInTheDocument();
    expect(screen.getByText("Мезоцикл")).toBeInTheDocument();
    expect(screen.getByText("Двойная прогрессия")).toBeInTheDocument();

    const offer = await screen.findByRole("region", { name: "Предложение разгрузки" });
    expect(offer).toHaveTextContent("RIR 0–1");
    await user.click(within(offer).getByRole("button", { name: "Сделать эту неделю разгрузкой" }));

    expect(
      callsWith("POST", `/api/blocks/placements/${PLACEMENT_ID}/deload-suggestion/accept`),
    ).toHaveLength(1);
    await waitFor(() => {
      expect(
        screen.queryByRole("region", { name: "Предложение разгрузки" }),
      ).not.toBeInTheDocument();
    });
  });
});
