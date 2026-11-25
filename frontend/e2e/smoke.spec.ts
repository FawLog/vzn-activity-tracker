import { expect, test } from "@playwright/test";

test("protected group workspace redirects anonymous visitors", async ({ page }, testInfo) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Officer sign-in" })).toBeVisible();
  const protectedResponse = await page.request.get("/api/v1/groups");
  expect(protectedResponse.status()).toBe(401);
  await page.screenshot({ path: testInfo.outputPath("login.png"), fullPage: true });
});

test("administrator onboards and manages a linked academy", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
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
    await page.getByLabel(/^ID\b/).fill("e2e-roster-fid");
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
  await expect(page.getByRole("columnheader", { name: "Power", exact: true })).toHaveAttribute("aria-sort", "descending");
  await expect(page.getByRole("columnheader", { name: "ID", exact: true })).toBeVisible();
  await expect(rosterPlayer.locator(".roster-avatar svg")).toBeVisible();
  for (const [label, column] of [["Power", "power"], ["Rank", "alliance_rank"], ["Furnace", "furnace_level"], ["Kills", "kills"], ["Nickname", "nickname"]]) {
    await test.step(`Sort roster by ${label}`, async () => {
      const header = page.getByRole("columnheader", { name: label, exact: true });
      const button = header.getByRole("button");
      for (const direction of label === "Nickname" ? ["asc"] : label === "Power" ? ["asc", "desc"] : ["desc", "asc"]) {
        await button.scrollIntoViewIfNeeded({ timeout: 8_000 });
        if (testInfo.project.name === "mobile-390") {
          await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
        }
        await Promise.all([
          page.waitForResponse((response) => {
            const url = new URL(response.url());
            return url.pathname.endsWith("/players") && url.searchParams.get("sort") === column && url.searchParams.get("direction") === direction && response.ok();
          }, { timeout: 8_000 }),
          button.click({ timeout: 8_000 }),
        ]);
        await expect(header).toHaveAttribute("aria-sort", direction === "asc" ? "ascending" : "descending");
        await expect(page.locator("section.data-panel--page")).toHaveAttribute("aria-busy", "false");
      }
    });
  }
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Nickname", exact: true })).toHaveAttribute("aria-sort", "ascending");
  await expect(rosterPlayer).toBeVisible();
  await page.route("https://avatar.example.test/scout.png", route => route.fulfill({
    contentType: "image/png",
    body: Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII=", "base64"),
  }));
  await page.route("**/api/v1/groups/*/players?*", async route => {
    const response = await route.fetch();
    const body = await response.json();
    for (const player of body.items ?? []) if (player.fid === "e2e-roster-fid") {
      player.avatar_url = "https://avatar.example.test/scout.png";
      player.furnace_level = 55;
      player.alliance_rank = "5";
    }
    await route.fulfill({ response, json: body });
  });
  await page.reload();
  const row = page.getByRole("row").filter({ has: rosterPlayer });
  await expect(row.getByText("FC5", { exact: true })).toBeVisible();
  await expect(row.locator(".roster-rank--r5")).toHaveText("R5");
  await expect.poll(() => row.locator(".roster-avatar img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await page.unroute("**/api/v1/groups/*/players?*");
  await page.unroute("https://avatar.example.test/scout.png");
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
  await page.goto("/events");
  await page.getByRole("button", {name:"Foundry Battle",exact:true}).first().click();
  await expect(page.getByRole("heading",{name:"Manual results"})).toBeVisible();
  await page.getByRole("button",{name:"Add session"}).click();
  await page.getByRole("button",{name:"Load group players"}).click();
  await page.getByRole("button",{name:"Add Roster Scout",exact:true}).click();
  await page.getByLabel("Roster Scout Personal points").fill("4500000000");
  const [saveResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "PUT" && /\/events\/[^/]+\/sessions\/[^/]+$/.test(response.url())),
    page.getByRole("button",{name:"Save draft"}).click(),
  ]);
  expect(saveResponse.status(), await saveResponse.text()).toBe(200);
  await expect(page.getByText("Draft saved.",{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveValue("4500000000");
  await page.screenshot({ path: testInfo.outputPath("alliance-event.png"), fullPage: true });
});
