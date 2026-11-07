import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NutritionPage } from "./NutritionPage";

const EMPTY_INTAKE = { protein_g: null, fat_g: null, carbs_g: null, calories: null };
const STUB_TARGET = {
  available: false,
  reason: "нет замера InBody",
  protein_g: null,
  fat_g: null,
  carbs_g: null,
  calories: null,
};

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/nutrition"]}>
        <NutritionPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("NutritionPage", () => {
  let resolveSave: (response: Response) => void = () => {};
  let savedBody: unknown;

  beforeEach(() => {
    savedBody = null;
    const pending = new Promise<Response>((resolve) => {
      resolveSave = resolve;
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).endsWith("/api/nutrition/targets")) return jsonResponse(STUB_TARGET);
        if (String(url).endsWith("/api/nutrition/intake") && init?.method === "PUT") {
          savedBody = JSON.parse(init.body as string);
          return pending;
        }
        if (String(url).endsWith("/api/nutrition/intake")) return jsonResponse(EMPTY_INTAKE);
        return jsonResponse({ detail: "Не найдено" }, 404);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows calculated calories from the typed grams before save returns", async () => {
    const user = userEvent.setup();
    renderPage();

    expect(await screen.findByRole("heading", { name: "Питание" })).toBeInTheDocument();
    expect(await screen.findByText("Расчёт появится после замера InBody.")).toBeInTheDocument();
    expect(screen.getAllByRole("textbox")).toHaveLength(3);

    await user.type(screen.getByLabelText("Белки, г"), "100");
    await user.type(screen.getByLabelText("Жиры, г"), "50");
    await user.type(screen.getByLabelText("Углеводы, г"), "200");

    expect(screen.getByText("1650 ккал")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Сохраняем…");
    expect(screen.getByText("1650 ккал")).toBeInTheDocument();
    expect(savedBody).toEqual({ protein_g: 100, fat_g: 50, carbs_g: 200 });

    resolveSave(jsonResponse({ protein_g: 100, fat_g: 50, carbs_g: 200, calories: 1650 }));
    await waitFor(() => {
      expect(screen.getByRole("status")).toHaveTextContent("Сохранено");
    });
    expect(screen.getAllByRole("textbox")).toHaveLength(3);
    expect(screen.queryByRole("textbox", { name: /цел/i })).not.toBeInTheDocument();
  });

  it("keeps the target block as a stub without editable goal fields", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "Целевое БЖУ" })).toBeInTheDocument();
    expect(await screen.findByText("Расчёт появится после замера InBody.")).toBeInTheDocument();
    expect(screen.getByLabelText("Белки, г")).toHaveAttribute("inputMode", "decimal");
    expect(screen.getByLabelText("Белки, г").className).toContain("min-h-11");
  });
});
