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
  // Exercise the actual overview layout and both emblem states at every configured viewport.
  await page.route("**/api/v1/groups/*/overview*", async route=>{
    const response=await route.fetch();
    const body=await response.json();
    body.alliance={external_name:"WZN",external_tag:"WZN",state_id:"1001",power:16761986250,member_count:100,power_rank:1,leader_name:"Scout",flag_url:"https://gof-formal-avatar.akamaized.net/test-flag.png",source_observed_at:"2026-11-26T04:00:00Z",previous_source_observed_at:"2026-11-25T22:00:00Z",received_at:"2026-11-26T04:01:00Z",power_change:60406175};
    await route.fulfill({response,json:body});
  });
  await page.route("https://gof-formal-avatar.akamaized.net/test-flag.png",route=>route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII=","base64")}));
  await page.reload();
  await expect(page.getByText("since previous sync · 6h")).toBeVisible();
  await expect.poll(()=>page.locator(".alliance-emblem img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
  await expect(page.locator(".alliance-intelligence .stats-grid > img")).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("overview-intelligence.png"),fullPage:true});
  await page.unroute("https://gof-formal-avatar.akamaized.net/test-flag.png");
  await page.route("https://gof-formal-avatar.akamaized.net/test-flag.png",route=>route.fulfill({status:404,body:"not found"}));
  await page.reload();
  await expect(page.getByRole("img",{name:"WZN alliance emblem unavailable"})).toBeVisible();
  await expect(page.locator(".alliance-emblem img")).toHaveCount(0);
  await page.unroute("https://gof-formal-avatar.akamaized.net/test-flag.png");
  await page.unroute("**/api/v1/groups/*/overview*");
  await page.reload();
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
  await page.route("**/api/v1/groups/*/players/e2e-roster-fid", async route => {
    const response = await route.fetch();
    const body = await response.json();
    Object.assign(body, { avatar_url: "https://avatar.example.test/scout.png", power: 331794134, kills: 33469020, furnace_level: 55, alliance_rank: "4", state_id: "4284", primary_alliance_name: "ValiantZenith", stat_history: [{ power: 331794134, kills: 33469020, furnace_level: 55, alliance_rank: "4", source_observed_at: "2026-11-25T12:00:00Z", alliance_id: "test" }], membership_history: [{ alliance_name: "ValiantZenith", alliance_tag: "VZN", observed_at: "2026-11-25T12:00:00Z" }] });
    await route.fulfill({ response, json: body });
  });
  await rosterPlayer.click();
  await expect(page.getByRole("heading", { name: "Roster Scout" })).toBeVisible();
  await expect.poll(() => page.locator(".profile-avatar img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(page.locator(".profile-stats > div")).toHaveCount(6);
  await expect(page.locator(".profile-stats")).toContainText("ValiantZenith");
  for (const name of ["Game history", "Membership observations"]) {
    const heading = page.getByRole("heading", { name, exact: true });
    await expect(heading).toBeVisible();
    await expect(heading.locator("xpath=../..")).toHaveClass("section-header");
    expect(await heading.evaluate(el => el.getBoundingClientRect().left - el.closest("section")!.getBoundingClientRect().left)).toBeGreaterThanOrEqual(16);
  }
  await expect.poll(() => page.evaluate(() => {
    if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
    return Array.from(document.querySelectorAll("body *")).filter(el => {
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.right > window.innerWidth + 1;
    }).slice(0, 15).map(el => ({ tag: el.tagName, className: el.getAttribute("class"), right: Math.round(el.getBoundingClientRect().right) }));
  }), { message: "Profile and workspace must fit the viewport" }).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("player-profile.png"), fullPage: true });
  await page.unroute("**/api/v1/groups/*/players/e2e-roster-fid");
  await page.reload();
  await expect(page.locator(".profile-avatar svg")).toBeVisible();
  await page.getByRole("main").getByRole("button", { name: "Players", exact: true }).click();
  await expect(rosterPlayer).toBeVisible();
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

  // Verify Overall default, low-score sorting, missing evidence and responsive table.
  await page.route("**/api/v1/groups/*/analytics?*",async route=>{
    const response=await route.fetch();
    const body=await response.json();
    const blank={observed_events:0,observed_sessions:0};
    const counts=(positive:number,negative:number)=>({positive,negative,unknown:0,excused:0,known:positive+negative,rate:positive+negative?100*positive/(positive+negative):null});
    body.players=["Review Low","Review High","Review Unknown"].map((nickname,i)=>({fid:"screen-"+i,nickname,group_status:"active",primary_alliance_id:body.alliance_id,metrics:{bear_trap:i===2?blank:{observed_events:1,observed_sessions:1,attendance:counts(i,1-i)},alliance_championship:blank,alliance_mobilization:blank,foundry:blank,canyon:blank}}));
    body.events=[{id:"screen-event",event_type:"bear_trap",occurred_on:"2026-11-24",recorded_players:2,unknown_home_players:0,session_count:1,metrics:blank,activity_cells:{"screen-0":"negative","screen-1":"positive"}}];
    await route.fulfill({response,json:body});
  });
  await page.goto("/rankings");
  await expect(page.getByRole("button",{name:"Overall",exact:true})).toHaveAttribute("aria-pressed","true");
  const overallTable=page.locator(".rankings-panel tbody");
  await expect(overallTable.locator("tr").first()).toContainText("Review Low");
  await expect(overallTable.locator("tr").last()).toContainText("Review Unknown");
  await expect(overallTable.locator("tr").last()).toContainText("No evidence");
  await page.getByRole("button",{name:/Activity score/}).click();
  await expect(overallTable.locator("tr").first()).toContainText("Review High");
  await page.getByLabel("Find player").fill("Review Low");
  await expect(overallTable.locator("tr")).toHaveCount(1);
  await page.getByLabel("Find player").clear();
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("overall-ranking.png"),fullPage:true});
  await page.getByRole("button",{name:"Attendance",exact:true}).click();
  await expect(page.getByLabel("Event / metric")).toBeVisible();
  await page.unroute("**/api/v1/groups/*/analytics?*");

  await page.goto("/admin?mode=events");
  await page.getByLabel(/^Event type/).selectOption("foundry");
  await page.getByLabel(/^Event date/).fill("2026-11-24");
  await page.getByRole("button", { name: "Create event" }).click();
  await expect(page.getByText("Event record created for the selected alliance.")).toBeVisible();
  await page.goto("/events");
  await page.getByRole("button", {name:"Foundry Battle",exact:true}).first().click();
  await expect(page.getByRole("heading",{name:"Manual results"})).toBeVisible();
  await page.getByRole("button",{name:"Add Legion 1"}).click();
  await page.route("**/api/v1/ocr/status", route=>route.fulfill({json:{configured:true,provider:"google_vision",max_image_bytes:921600}}));
  await page.route("**/ocr/preview", async route=>{
    expect(route.request().headers()["content-type"]).toBe("image/png");
    expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
    await route.fulfill({json:{provider:"google_vision",text:"Roster Scout 4500000000",tokens:[],warnings:[]}});
  });
  await page.reload();
  await page.getByLabel("Choose screenshots").setInputFiles([{name:"first.png",mimeType:"image/png",buffer:Buffer.from("image1")},{name:"second.png",mimeType:"image/png",buffer:Buffer.from("image2")}]);
  await page.getByRole("button",{name:"Recognize screenshots"}).click();
  await expect(page.getByText("2 of 2 screenshots recognized")).toBeVisible();
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveCount(0);
  await page.getByRole("button",{name:"Clear screenshots"}).click();
  await page.unroute("**/ocr/preview");
  await page.unroute("**/api/v1/ocr/status");
  await page.getByLabel("List type").selectOption("metrics");
  await page.getByLabel("Paste player list").fill("e2e-roster-fid\t4500000000");
  await page.getByRole("button",{name:"Import list"}).click();
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveValue("4500000000");
  await expect(page.getByLabel("Roster Scout Attendance")).toHaveValue("confirmed_present");
  await page.getByLabel("Paste player list").fill("unknown-fid\t1");
  await page.getByRole("button",{name:"Import list"}).click();
  await expect(page.getByRole("alert")).toContainText("not found");
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveValue("4500000000");
  const [saveResponse] = await Promise.all([
    page.waitForResponse(response => response.request().method() === "PUT" && /\/events\/[^/]+\/sessions\/[^/]+$/.test(response.url())),
    page.getByRole("button",{name:"Save draft"}).click(),
  ]);
  expect(saveResponse.status(), await saveResponse.text()).toBe(200);
  await expect(page.getByText("Draft saved.",{exact:true})).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveValue("4500000000");
  await page.screenshot({ path: testInfo.outputPath("alliance-event.png"), fullPage: true });
  page.once("dialog", dialog=>dialog.accept());
  await page.getByRole("button",{name:"Delete event",exact:true}).click();
  await expect(page).toHaveURL(/\/events$/);
});
