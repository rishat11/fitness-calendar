import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InbodyPage } from "./InbodyPage";

const SAVED = {
  id: "scan-1",
  measured_on: "2026-10-26",
  measured_time: "08:30:00",
  weight_kg: 84.7,
  smm_kg: 43,
  bfm_kg: 9.9,
  pbf_percent: 11.7,
  tbw_l: 54.8,
  visceral_fat_level: 3,
  bmr_kcal: 1985,
  segments: null,
  deltas: [],
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
      <MemoryRouter>
        <InbodyPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("InbodyPage", () => {
  let scans: unknown[] = [];
  let posted: unknown = null;
  let updated: unknown = null;

  beforeEach(() => {
    scans = [];
    posted = null;
    updated = null;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (String(url).endsWith("/api/inbody/parse") && init?.method === "POST") {
          return jsonResponse({
            measured_on: "2026-11-07",
            measured_time: "09:15:00",
            weight_kg: 84.7,
            smm_kg: 38.2,
            bfm_kg: 16.4,
            pbf_percent: 19.4,
            tbw_l: 48.5,
            visceral_fat_level: 7,
            bmr_kcal: 1750,
            missing: [],
          });
        }
        if (String(url).includes("/api/inbody/") && init?.method === "PUT") {
          updated = JSON.parse(init.body as string);
          return jsonResponse({ ...SAVED, ...(updated as object) });
        }
        if (String(url).endsWith("/api/inbody") && init?.method === "POST") {
          posted = JSON.parse(init.body as string);
          const created = { ...SAVED, ...(posted as object), id: "scan-new" };
          scans = [created];
          return jsonResponse(created, 201);
        }
        if (String(url).endsWith("/api/inbody")) return jsonResponse(scans);
        return jsonResponse({ detail: "Не найдено" }, 404);
      }),
    );
  });

  it("shows the memo and an empty list", async () => {
    renderPage();

    expect(await screen.findByRole("heading", { name: "InBody" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Как правильно делать замер InBody" })).toBeInTheDocument();
    expect(screen.getByText(/один и тот же прибор/)).toBeInTheDocument();
    expect(await screen.findByText("Замеров пока нет.")).toBeInTheDocument();
    expect(screen.getByText(/нескольким замерам/)).toBeInTheDocument();
  });

  it("saves a manual scan", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Новый замер" });

    await user.clear(screen.getByLabelText("Дата"));
    await user.type(screen.getByLabelText("Дата"), "2026-10-26");
    await user.type(screen.getByLabelText("Вес, кг"), "84,7");
    await user.type(screen.getByLabelText("Мышцы, кг"), "43");
    await user.type(screen.getByLabelText("Содержание жира, кг"), "9,9");
    await user.type(screen.getByLabelText("Жир, %"), "11,7");
    await user.type(screen.getByLabelText("Вода, л"), "54,8");
    await user.type(screen.getByLabelText("Висцеральный жир, уровень"), "3");
    await user.type(screen.getByLabelText("Обмен веществ, ккал"), "1985");

    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    await waitFor(() => {
      expect(posted).toMatchObject({
        measured_on: "2026-10-26",
        weight_kg: 84.7,
        smm_kg: 43,
        bfm_kg: 9.9,
        pbf_percent: 11.7,
        tbw_l: 54.8,
        visceral_fat_level: 3,
        bmr_kcal: 1985,
      });
    });
    expect(await screen.findByText(/2026-10-26 · 84\.7 кг/)).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Сохранено");
  });

  it("saves an edited scan without a save button", async () => {
    scans = [{ ...SAVED }];
    const user = userEvent.setup();
    renderPage();

    await user.click(await screen.findByRole("button", { name: "Изменить" }));
    const weight = screen.getByLabelText("Вес, кг");
    await user.clear(weight);
    await user.type(weight, "85");

    await waitFor(() => {
      expect(updated).toMatchObject({ weight_kg: 85, measured_on: "2026-10-26" });
    });
    expect(weight).toHaveValue("85");
    expect(screen.getByRole("button", { name: "Отмена" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("Сохранено");
  });

  it("fills the form from a parsed pdf and saves the scan", async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("heading", { name: "Новый замер" });

    const file = new File(["%PDF-1.4"], "sheet.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("PDF-лист InBody"), file);

    expect(await screen.findByText(/Цифры с листа подставлены/)).toBeInTheDocument();
    expect(screen.getByLabelText("Вес, кг")).toHaveValue("84,7");
    expect(screen.getByLabelText("Жир, %")).toHaveValue("19,4");
    expect(screen.getByLabelText("Дата")).toHaveValue("2026-11-07");
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(screen.queryByRole("group", { name: "Условия замера" })).not.toBeInTheDocument();

    await waitFor(() => {
      expect(posted).toMatchObject({
        measured_on: "2026-11-07",
        weight_kg: 84.7,
        pbf_percent: 19.4,
        bmr_kcal: 1750,
      });
    });
    expect(await screen.findByText(/2026-11-07 09:15 · 84\.7 кг/)).toBeInTheDocument();
  });
});
