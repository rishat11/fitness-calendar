import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LoginPage } from "./LoginPage";

function renderLoginPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("LoginPage", () => {
  beforeEach(() => {
    // /api/auth/me возвращает 401: пользователь не вошёл.
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response(JSON.stringify({ detail: "Требуется вход" }), { status: 401 })),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders email and password fields and the submit button", async () => {
    renderLoginPage();

    expect(await screen.findByRole("heading", { name: "Вход" })).toBeInTheDocument();
    expect(screen.getByLabelText("Email")).toBeInTheDocument();
    expect(screen.getByLabelText("Пароль")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Войти" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Регистрация" })).toHaveAttribute("href", "/register");
  });

  it("shows validation errors and does not send the request for invalid input", async () => {
    const user = userEvent.setup();
    renderLoginPage();

    await screen.findByRole("button", { name: "Войти" });
    await user.type(screen.getByLabelText("Email"), "not-an-email");
    await user.type(screen.getByLabelText("Пароль"), "short");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(screen.getByText("Введите корректный email")).toBeInTheDocument();
    expect(
      screen.getByText("Пароль должен быть не короче 8 символов"),
    ).toBeInTheDocument();

    const fetchMock = vi.mocked(fetch);
    await waitFor(() => {
      const loginCalls = fetchMock.mock.calls.filter(([url]) => url === "/api/auth/login");
      expect(loginCalls).toHaveLength(0);
    });
  });
});
