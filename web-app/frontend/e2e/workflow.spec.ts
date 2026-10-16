import { test, expect, type Page } from "@playwright/test";
import fs from "node:fs";

async function login(page: Page, account: string) {
  await page.goto("/");
  await page.getByLabel("Учётная запись").selectOption(account);
  await page.getByLabel("Пароль", { exact: true }).fill("Bliny-demo-2026!");
  await page.getByRole("button", { name: "Войти в приложение" }).click();
  await expect(
    page.getByRole("heading", { name: "Всё под контролем" }),
  ).toBeVisible();
  await page.getByLabel("Торговая точка").selectOption("point-1");
  await expect(
    page.getByRole("heading", { name: "Динамика продаж" }),
  ).toBeVisible();
}

test("warehouse → invoice → partial receipt, desktop and mobile", async ({
  browser,
}) => {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 1050 },
  });
  const page = await context.newPage();
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await login(page, "point1");
  const amount = 127;
  await page.getByRole("button", { name: "Новая заявка", exact: true }).click();
  await page
    .getByRole("dialog")
    .getByLabel("Творог", { exact: true })
    .fill(String(amount));
  const created = page.waitForResponse(
    (r) => r.url().endsWith("/api/requests") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Создать заявку", exact: true })
    .click();
  const order = await (await created).json();
  expect(order.id).toBeTruthy();
  await expect(page.getByRole("dialog")).not.toBeVisible();
  await page.getByTitle("Выйти", { exact: true }).click();
  await login(page, "warehouse");
  fs.mkdirSync("../docs/screenshots", { recursive: true });
  await page.screenshot({
    path: "../docs/screenshots/overview.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: order.number, exact: true }).click();
  for (const label of [
    "Принять заявку",
    "Создать накладную",
    "Подтвердить отправку",
  ]) {
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(
      page.getByRole("button", { name: label, exact: true }),
    ).not.toBeVisible();
  }
  await expect(
    page.getByRole("heading", { name: new RegExp("Накладная Н-") }),
  ).toBeVisible();
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "Закрыть", exact: true })
    .last()
    .click();
  await page.getByTitle("Выйти", { exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await login(page, "point1");
  await page.screenshot({
    path: "../docs/screenshots/mobile.png",
    fullPage: true,
  });
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.getByRole("button", { name: order.number, exact: true }).click();
  await page.getByLabel("Принято: Творог", { exact: true }).fill("50");
  await page
    .getByLabel("Расхождения / комментарий", { exact: true })
    .fill("Демонстрация: остаток ожидается следующей приёмкой.");
  await page
    .getByRole("button", { name: "Подтвердить приёмку", exact: true })
    .click();
  await expect(
    page.getByRole("heading", { name: "История приёмки" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog").getByRole("cell", { name: String(amount - 50), exact: true }),
  ).toBeVisible();
  await page.getByLabel("Принято: Творог", { exact: true }).fill(String(amount - 50));
  await page.getByRole("button", { name: "Подтвердить приёмку", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Подтвердить фактическую приёмку" })).not.toBeVisible();
  expect(errors).toEqual([]);
  await context.close();
});

test("analytics and forecast display calculated demo data", async ({
  page,
}) => {
  await login(page, "analyst");
  await page.getByRole("button", { name: "Аналитика", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Ассортимент", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Все позиции", exact: true }).click();
  await expect(
    page.getByRole("cell", { name: "Блин с творогом", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Прогноз спроса", exact: true })
    .click();
  await page.getByRole("button", { name: "14 дней", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Временная проверка baseline" }),
  ).toBeVisible();
  await expect(
    page.getByText(/CatBoost\/GRU ещё не реализованы/),
  ).toBeVisible();
});
