import { expect, test } from "@playwright/test";

test("protected group workspace redirects anonymous visitors", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Officer sign-in" })).toBeVisible();
  const protectedResponse = await page.request.get("/api/v1/groups");
  expect(protectedResponse.status()).toBe(401);
  await page.screenshot({ path: testInfo.outputPath("login.png"), fullPage: true });
});

test("administrator onboards and manages a linked academy", async ({ page }, testInfo) => {
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!password) throw new Error("E2E_ADMIN_PASSWORD is required for the authenticated flow");

  await page.goto("/login");
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
  const setupButton = page.getByRole("button", { name: "Start setup" });
  if (await setupButton.isVisible()) {
    await setupButton.click();
    await expect(page.getByRole("heading", { name: "Set up the first alliance group" })).toBeVisible();
    await page.getByLabel("Group name").fill("WZN");
    await page.getByLabel("Primary alliance name").fill("WZN");
    await page.getByLabel("Tag").fill("WZN");
    await page.getByLabel("State ID").fill("1001");
    await page.getByRole("button", { name: "Confirm group setup" }).click();
    await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
  }
  await page.screenshot({ path: testInfo.outputPath("group-overview.png"), fullPage: true });

  await page.goto("/groups");
  await expect(page.getByRole("heading", { name: "Alliance groups" })).toBeVisible();
  await expect(page.getByRole("button", { name: "WZN WZN" })).toBeVisible();
  const academy = page.getByRole("button", { name: "WZN Academy WZNA" });
  if (await academy.count() === 0) {
    await page.getByRole("button", { name: "Add alliance" }).click();
    await page.getByPlaceholder("Alliance name").fill("WZN Academy");
    await page.getByPlaceholder("Tag").fill("WZNA");
    await page.getByPlaceholder("State ID").fill("1001");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.getByText("Additional alliance added.")).toBeVisible();
  }
  const selectedAcademy = academy.first();
  await expect(selectedAcademy).toBeVisible();
  await selectedAcademy.click();
  await page.screenshot({ path: testInfo.outputPath("group-management.png"), fullPage: true });

  await page.goto("/admin?mode=events");
  await page.getByLabel(/^Event type/).selectOption("foundry");
  await page.getByLabel(/^Event date/).fill("2026-11-24");
  await page.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText("Event record created for the selected alliance.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("alliance-event.png"), fullPage: true });
});
