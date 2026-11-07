import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsPage } from "./SettingsPage";

const SAVED_PROFILE = {
  goal: "cut",
  height_cm: 180,
  age: 32,
  sex: "male",
  weight_unit: "kg",
  theme: "system",
};

function renderSettingsPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/settings"]}>
        <Routes>
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/login" element={<h1>Вход</h1>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("SettingsPage", () => {
  let profile: typeof SAVED_PROFILE;

  beforeEach(() => {
    profile = { ...SAVED_PROFILE };
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === "/api/profile" && init?.method === "PUT") {
          profile = JSON.parse(init.body as string);
          return jsonResponse(profile);
        }
        if (url === "/api/profile") {
          return jsonResponse(profile);
        }
        if (url === "/api/export") {
          return jsonResponse({
            format_version: 1,
            exported_at: "2026-11-07T12:00:00Z",
            profile,
            exercises: [],
            workout_templates: [],
            planned_workouts: [],
            plan_change_logs: [],
            performed_workouts: [],
          });
        }
        if (url === "/api/export/workouts.csv") {
          return new Response("Дата,Тренировка\n", {
            status: 200,
            headers: { "Content-Type": "text/csv" },
          });
        }
        if (url === "/api/import?mode=replace" && init?.method === "POST") {
          return jsonResponse({
            exercises: 0,
            workout_templates: 0,
            planned_workouts: 0,
            performed_workouts: 0,
          });
        }
        if (url === "/api/auth/account" && init?.method === "DELETE") {
          const body = JSON.parse(init.body as string) as { password: string };
          if (body.password !== "password1") {
            return jsonResponse({ detail: "Неверный пароль" }, 401);
          }
          return new Response(null, { status: 204 });
        }
        return jsonResponse({ detail: "Не найдено" }, 404);
      }),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("shows saved profile values", async () => {
    renderSettingsPage();

    expect(await screen.findByRole("heading", { name: "Настройки" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Цель")).toHaveValue("cut");
    expect(screen.getByLabelText(/Рост/)).toHaveValue("180");
    expect(screen.getByLabelText(/Возраст/)).toHaveValue("32");
    expect(screen.getByLabelText("Тема оформления")).toHaveValue("system");
  });

  it("sends the full profile on save", async () => {
    const user = userEvent.setup();
    renderSettingsPage();

    await screen.findByLabelText("Цель");
    await user.selectOptions(screen.getByLabelText("Цель"), "muscle_gain");
    await user.clear(screen.getByLabelText(/Рост/));
    await user.type(screen.getByLabelText(/Рост/), "182");
    await user.selectOptions(screen.getByLabelText("Тема оформления"), "dark");

    expect(await screen.findByRole("status")).toHaveTextContent("Сохранено");
    expect(screen.queryByRole("button", { name: "Сохранить" })).not.toBeInTheDocument();
    expect(profile).toEqual({
      goal: "muscle_gain",
      height_cm: 182,
      age: 32,
      sex: "male",
      weight_unit: "kg",
      theme: "dark",
    });
  });

  it("sends null for empty optional fields", async () => {
    const user = userEvent.setup();
    renderSettingsPage();

    await screen.findByLabelText("Цель");
    await user.selectOptions(screen.getByLabelText("Цель"), "");
    await user.clear(screen.getByLabelText(/Возраст/));

    await waitFor(() => {
      expect(profile.goal).toBeNull();
      expect(profile.age).toBeNull();
    });
  });

  it("rejects out-of-range height without sending a request", async () => {
    const user = userEvent.setup();
    renderSettingsPage();

    await screen.findByLabelText("Цель");
    await user.clear(screen.getByLabelText(/Рост/));
    await user.type(screen.getByLabelText(/Рост/), "99");

    expect(await screen.findByText("Укажите рост от 100 до 250 см")).toBeInTheDocument();
    await waitFor(() => {
      const puts = vi.mocked(fetch).mock.calls.filter(([, init]) => init?.method === "PUT");
      expect(puts).toHaveLength(0);
    });
  });

  it("downloads json and csv backups", async () => {
    const user = userEvent.setup();
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:backup");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
    renderSettingsPage();

    await user.click(await screen.findByRole("button", { name: "Скачать JSON" }));
    expect(await screen.findByText("Файл JSON сохранён")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Скачать CSV" }));
    expect(await screen.findByText("Файл CSV сохранён")).toBeInTheDocument();

    const urls = vi.mocked(fetch).mock.calls.map(([url]) => url);
    expect(urls).toContain("/api/export");
    expect(urls).toContain("/api/export/workouts.csv");
  });

  it("replaces data from a json file after confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettingsPage();

    const file = new File(
      [
        JSON.stringify({
          format_version: 1,
          profile,
          exercises: [],
        }),
      ],
      "backup.json",
      { type: "application/json" },
    );
    await user.upload(await screen.findByLabelText("Импортировать JSON"), file);

    expect(await screen.findByText("Данные заменены из файла")).toBeInTheDocument();
    const imports = vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/import?mode=replace");
    expect(imports).toHaveLength(1);
  });

  it("does not import when confirmation is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderSettingsPage();

    const file = new File(
      [JSON.stringify({ format_version: 1, profile, exercises: [] })],
      "backup.json",
      { type: "application/json" },
    );
    await user.upload(await screen.findByLabelText("Импортировать JSON"), file);

    expect(screen.queryByText("Данные заменены из файла")).not.toBeInTheDocument();
    const imports = vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/import?mode=replace");
    expect(imports).toHaveLength(0);
  });

  it("deletes the account after password confirmation", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(true);
    renderSettingsPage();

    await user.type(await screen.findByLabelText("Пароль для удаления"), "password1");
    await user.click(screen.getByRole("button", { name: "Удалить аккаунт" }));

    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
    const calls = vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/auth/account");
    expect(calls).toHaveLength(1);
    expect(calls[0][1]?.method).toBe("DELETE");
  });

  it("does not delete the account when confirmation is cancelled", async () => {
    const user = userEvent.setup();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    renderSettingsPage();

    await user.type(await screen.findByLabelText("Пароль для удаления"), "password1");
    await user.click(screen.getByRole("button", { name: "Удалить аккаунт" }));

    expect(screen.queryByRole("heading", { name: "Вход" })).not.toBeInTheDocument();
    const calls = vi.mocked(fetch).mock.calls.filter(([url]) => url === "/api/auth/account");
    expect(calls).toHaveLength(0);
  });
});
