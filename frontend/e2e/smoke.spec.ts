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
    await expect(page.getByRole("heading", { name: "Workspace configured" })).toBeVisible();
    await expect(page.getByText(/Initial roster import:|Synchronization is not configured/)).toBeVisible();
    await page.getByRole("button", { name: "Continue to alliance settings" }).click();
    await expect(page.getByRole("heading", { name: "Alliance groups" })).toBeVisible();
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Operational overview" })).toBeVisible();
  }
  await page.screenshot({ path: testInfo.outputPath("group-overview.png"), fullPage: true });

  await page.goto("/players");
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible();
  const rosterPlayer = page.getByRole("button", { name: "Roster Scout" });
  if (await rosterPlayer.count() === 0) {
    await page.goto("/admin?mode=players");
    await page.getByLabel("FID").fill("e2e-roster-fid");
    await page.getByLabel("Nickname").fill("Roster Scout");
    await page.getByRole("button", { name: "Add player" }).click();
    await expect(page.getByText(/Player record created in the selected group.|This player already belongs to the selected group/)).toBeVisible();
    await page.goto("/players");
  }
  await expect(rosterPlayer).toBeVisible();
  await expect(page.getByText("Unconfirmed", { exact: true })).toBeVisible();
  const affiliation = page.getByLabel("Roster affiliation");
  await affiliation.selectOption("unconfirmed");
  await expect(rosterPlayer).toBeVisible();
  await affiliation.selectOption({ label: "Primary alliance · WZN" });
  await expect(page.getByText("No players in this view")).toBeVisible();
  await affiliation.selectOption("all");
  await expect(rosterPlayer).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("player-affiliation-filter.png"), fullPage: true });

  await page.goto("/groups");
  await expect(page.getByRole("heading", { name: "Alliance groups" })).toBeVisible();
  await expect(page.getByRole("button", { name: "WZN WZN" })).toBeVisible();
  const academy = page.getByRole("button", { name: /^WZN Academy(?: Updated)? WZNA$/ });
  if (await academy.count() === 0) {
    await page.getByRole("button", { name: "Add alliance" }).click();
    await page.getByPlaceholder("Alliance name").fill("WZN Academy");
    await page.getByPlaceholder("Tag").fill("WZNA");
    await page.getByPlaceholder("State ID").fill("1001");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await expect(page.locator(".group-main > .notice").filter({ hasText: /Initial roster import:|Synchronization is not configured/ })).toBeVisible();
  }
  await expect(academy.first()).toBeVisible();
  if (testInfo.project.name === "desktop-1440") {
    await page.getByRole("button", { name: "Edit WZN Academy" }).click();
    await page.getByLabel("Alliance name").fill("WZN Academy Updated");
    await page.getByLabel("Alliance tag").fill("WZNA");
    await page.getByLabel("Alliance state ID").fill("1002");
    await page.getByRole("button", { name: "Save alliance" }).click();
    await expect(page.getByText("Alliance settings saved.")).toBeVisible();
    await expect(page.getByRole("button", { name: "WZN Academy Updated WZNA" })).toBeVisible();
  }
  const allianceSwitcher = page.getByLabel("Current alliance");
  const academyOption = allianceSwitcher.locator("option").filter({ hasText: "WZNA" });
  await allianceSwitcher.selectOption(await academyOption.first().getAttribute("value") ?? "");
  await expect(allianceSwitcher.locator("option:checked")).toContainText("WZNA");
  await page.screenshot({ path: testInfo.outputPath("group-management.png"), fullPage: true });

  await page.goto("/admin?mode=events");
  await page.getByLabel(/^Event type/).selectOption("foundry");
  await page.getByLabel(/^Event date/).fill("2026-11-24");
  await page.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText("Event record created for the selected alliance.")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("alliance-event.png"), fullPage: true });
});
