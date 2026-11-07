import { expect, type Locator, type Page, test } from "@playwright/test";
import { addDays, todayIso, WEEKDAY_LABELS, weekdayIndex } from "../src/features/calendar/dates";

const PASSWORD = "password1";

test("login fields are reached from the keyboard and keep a visible focus ring", async ({ page }) => {
  await page.goto("/login");
  await page.keyboard.press("Tab");
  const email = page.locator("#auth-email");
  await expect(email).toBeFocused();
  const outlineWidth = await email.evaluate((element) => getComputedStyle(element).outlineWidth);
  expect(outlineWidth).not.toBe("0px");

  await page.keyboard.press("Tab");
  await expect(page.locator("#auth-password")).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "Войти" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Введите корректный email")).toBeVisible();
});

test("mvp path: template, cycle, phone log, drag, shift, import, delete", async ({ page }) => {
  const email = `e2e-${Date.now()}@example.com`;
  const today = todayIso();
  const weekday = WEEKDAY_LABELS[weekdayIndex(today)];
  const otherDay = weekdayIndex(today) === 6 ? addDays(today, -1) : addDays(today, 1);

  await page.setViewportSize({ width: 360, height: 800 });
  await register(page, email);

  await page.getByRole("link", { name: "Тренировки" }).click();
  await page.getByLabel("Название тренировки").fill("День A");
  await page.getByRole("button", { name: "Создать" }).click();
  await expect(page.getByRole("heading", { name: "Упражнения" })).toBeVisible();

  const quick = page.getByRole("form", { name: "Быстрое создание упражнения" });
  await quick.getByLabel("Название").fill("Присед");
  await quick.getByLabel("Основная группа").selectOption({ label: "Квадрицепсы" });
  await quick.getByRole("button", { name: "Добавить" }).click();
  await expect(page.getByRole("listitem", { name: "Упражнение 1: Присед" })).toBeVisible();
  await page.getByRole("button", { name: "Сохранить" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Сохранено" })).toBeVisible();

  await page.getByRole("link", { name: "Календарь" }).click();
  await page.getByLabel("Тренировка из библиотеки").selectOption({ label: "День A" });
  // Чекбокс дня спрятан (sr-only): клик по подписи, как делает человек.
  await page.getByRole("group", { name: "Дни недели" }).getByText(weekday, { exact: true }).click();
  await page.getByLabel("Количество недель").fill("2");
  await page.getByRole("button", { name: "Создать цикл" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Создано тренировок" })).toHaveText(
    "Создано тренировок: 2",
  );

  await page.getByRole("link", { name: "Сегодня" }).click();
  await page.getByRole("link", { name: "Открыть", exact: true }).click();
  await expect(page.getByRole("heading", { name: "День A" })).toBeVisible();
  await expect(page.getByText("Присед")).toBeVisible();

  const weight = page.getByRole("textbox", { name: "Присед, подход 1: Вес", exact: true });
  const reps = page.getByRole("textbox", { name: "Присед, подход 1: повторы", exact: true });
  const saved = page.waitForResponse(
    (response) => response.url().includes("/sets/") && response.request().method() === "PUT" && response.ok(),
  );
  await weight.fill("80");
  await reps.fill("8");
  await page
    .getByRole("group", { name: "Присед, подход 1: RIR" })
    .getByRole("button", { name: "2", exact: true })
    .click();
  await saved;
  await expect(page.getByRole("status").filter({ hasText: "Сохранено" })).toBeVisible();

  await page.reload();
  await expect(weight).toHaveValue("80");
  await expect(reps).toHaveValue("8");
  await expect(
    page.getByRole("group", { name: "Присед, подход 1: RIR" }).getByRole("button", { name: "2", exact: true }),
  ).toHaveAttribute("aria-pressed", "true");

  await page.setViewportSize({ width: 1280, height: 800 });
  await page.getByRole("link", { name: "Календарь" }).click();
  await page.getByRole("button", { name: "Неделя" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("button", { name: "Неделя" })).toHaveAttribute("aria-pressed", "true");

  await dragEntry(page, page.getByRole("button", { name: "День A", exact: true }), otherDay);
  await expect(page.locator(`[data-date="${otherDay}"]`).getByRole("button", { name: "День A" })).toBeVisible();

  await page.locator(`[data-date="${otherDay}"]`).getByRole("button", { name: "День A" }).click();
  await page.getByRole("button", { name: "Эта и следующие" }).click();
  const preview = page.getByRole("dialog", { name: "Предпросмотр сдвига" });
  await expect(preview).toBeVisible();
  await expect(preview.getByRole("list", { name: "Было и станет" })).toBeVisible();
  await preview.getByRole("button", { name: "Применить" }).click();
  const toast = page.getByRole("status", { name: "План изменён" });
  await expect(toast).toBeVisible();
  await toast.getByRole("button", { name: "Отменить" }).click();
  await expect(page.locator(`[data-date="${otherDay}"]`).getByRole("button", { name: "День A" })).toBeVisible();

  const exported = await page.request.get("/api/export");
  expect(exported.ok()).toBeTruthy();
  const backup = await exported.body();

  await page.locator(`[data-date="${otherDay}"]`).getByRole("button", { name: "День A" }).click();
  await page.getByRole("link", { name: "Записать тренировку" }).click();
  const changed = page.waitForResponse(
    (response) => response.url().includes("/sets/") && response.request().method() === "PUT" && response.ok(),
  );
  await page.getByRole("textbox", { name: "Присед, подход 1: Вес", exact: true }).fill("90");
  await changed;

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("header").getByRole("link", { name: "Настройки" }).click();
  await page.getByLabel("Импортировать JSON").setInputFiles({
    name: "backup.json",
    mimeType: "application/json",
    buffer: backup,
  });
  await expect(page.getByText("Данные заменены из файла")).toBeVisible();

  await page.getByRole("link", { name: "Календарь" }).click();
  await page.getByRole("button", { name: "Неделя" }).click();
  await page.locator(`[data-date="${otherDay}"]`).getByRole("button", { name: "День A" }).click();
  await page.getByRole("link", { name: "Записать тренировку" }).click();
  await expect(page.getByRole("textbox", { name: "Присед, подход 1: Вес", exact: true })).toHaveValue(
    "80",
  );

  page.once("dialog", (dialog) => dialog.accept());
  await page.locator("header").getByRole("link", { name: "Настройки" }).click();
  await page.getByLabel("Пароль для удаления").fill(PASSWORD);
  await page.getByRole("button", { name: "Удалить аккаунт" }).click();
  await expect(page.getByRole("heading", { name: "Вход" })).toBeVisible();

  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Войти" }).click();
  await expect(page.getByText("Неверный email или пароль")).toBeVisible();
});

async function register(page: Page, email: string) {
  await page.goto("/register");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Пароль").fill(PASSWORD);
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.getByRole("heading", { name: "Привет," })).toBeVisible();
}

async function dragEntry(page: Page, card: Locator, targetDate: string) {
  const target = page.locator(`[data-date="${targetDate}"]`);
  await card.scrollIntoViewIfNeeded();
  await target.scrollIntoViewIfNeeded();
  const from = await card.boundingBox();
  const to = await target.boundingBox();
  if (!from || !to) {
    throw new Error("Не удалось найти карточку или день для перетаскивания");
  }
  const startX = from.x + from.width / 2;
  const startY = from.y + from.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 16, startY + 12, { steps: 5 });
  await page.mouse.move(to.x + Math.min(48, to.width / 2), to.y + 28, { steps: 24 });
  await page.mouse.up();
}
