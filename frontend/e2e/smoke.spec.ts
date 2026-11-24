import { expect, test } from "@playwright/test";

test("public overview and protected routes", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
  await expect(page.getByText("Private by default")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("public-overview.png"), fullPage: true });

  const protectedResponse = await page.request.get("/api/v1/players");
  expect(protectedResponse.status()).toBe(401);

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Officer sign-in" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("login.png"), fullPage: true });
});

test("administrator can create foundational records", async ({ page }, testInfo) => {
  const password = process.env.E2E_ADMIN_PASSWORD;
  if (!password) throw new Error("E2E_ADMIN_PASSWORD is required for the authenticated flow");

  await page.goto("/login");
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("authenticated-overview.png"), fullPage: true });

  await page.goto("/admin");
  await expect(page.getByRole("heading", { name: "Administration" })).toBeVisible();

  const suffix = `${testInfo.project.name}-${Date.now()}`.replace(/[^a-z0-9-]/gi, "").slice(-24);
  const nickname = `CI Ranger ${testInfo.project.name}`;
  await page.getByLabel(/^FID/).fill(`ci-${suffix}`);
  await page.getByLabel(/^Nickname/).fill(nickname);
  await page.getByRole("button", { name: "Add player" }).click();
  await expect(page.getByText("Player record created.")).toBeVisible();

  await page.getByRole("tab", { name: "Events" }).click();
  await page.getByLabel(/^Event type/).selectOption("svs_preparation");
  await page.getByLabel(/^Event date/).fill("2026-11-24");
  await page.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText("Event record created.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("admin.png"), fullPage: true });

  await page.goto("/players");
  await expect(page.getByText(nickname)).toBeVisible();
});
