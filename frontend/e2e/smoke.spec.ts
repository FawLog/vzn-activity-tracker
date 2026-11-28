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
  // Upcoming events use the same group-scoped calendar endpoint as Calendar.
  await page.route("**/api/v1/groups/*/calendar?*",async route=>{
    const response=await route.fetch();
    const groupId=new URL(route.request().url()).pathname.split("/")[4];
    const day=new Date(Date.now()+86400000).toISOString().slice(0,10);
    const base={id:"upcoming-review",group_id:groupId,series_id:null,sequence:0,event_type:"winter_siege",scope:"state",alliance_id:null,state_id:"1001",starts_at:day,ends_at:null,precision:"date",phase:"Upcoming verification",confidence:"estimated",schedule_status:"scheduled",source:"manual",revision:1};
    await route.fulfill({response,json:{items:[base,{...base,id:"cancelled-review",phase:"Cancelled verification",schedule_status:"cancelled"}]}});
  });
  await page.reload();
  const upcoming=page.getByRole("region",{name:"Upcoming events"});
  await expect(upcoming.getByRole("heading",{name:"Upcoming events"})).toBeVisible();
  await upcoming.getByLabel("Schedule scope").selectOption("group");
  await expect(upcoming.getByRole("button",{name:/Upcoming verification/})).toBeVisible();
  await expect(upcoming.getByText(/time not set/)).toBeVisible();
  await expect(upcoming.getByRole("button",{name:/Cancelled verification/})).toHaveCount(0);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.unroute("**/api/v1/groups/*/calendar?*");
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
  // Every grid row must be fully covered by real metric cells (only 1px dividers).
  await expect(page.locator(".alliance-intelligence .stats-grid > div")).toHaveCount(5);
  expect(await page.locator(".alliance-intelligence .stats-grid").evaluate(grid=>{
    const bounds=grid.getBoundingClientRect();
    const cells=Array.from(grid.children,cell=>cell.getBoundingClientRect());
    return [...new Set(cells.map(c=>c.top))].every(top=>{
      const row=cells.filter(c=>c.top===top).sort((a,b)=>a.left-b.left);
      return Math.abs(row[0].left-bounds.left)<=1 && Math.abs(row[row.length-1].right-bounds.right)<=1 && row.slice(1).every((cell,i)=>cell.left-row[i].right<=2);
    });
  })).toBe(true);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("overview-intelligence.png"),fullPage:true});
  await page.unroute("https://gof-formal-avatar.akamaized.net/test-flag.png");
  await page.route("https://gof-formal-avatar.akamaized.net/test-flag.png",route=>route.fulfill({status:404,body:"not found"}));
  await page.reload();
  await expect(page.getByRole("img",{name:"WZN alliance emblem unavailable"})).toBeVisible();
  await expect(page.locator(".alliance-emblem img")).toHaveCount(0);
  await page.unroute("https://gof-formal-avatar.akamaized.net/test-flag.png");
  await page.unroute("**/api/v1/groups/*/overview*");
  // Overview defaults to the same Overall index, with mixed event columns and quick view.
  await page.route("**/api/v1/groups/*/analytics?*",async route=>{
    const response=await route.fetch();
    const body=await response.json();
    const blank={observed_events:0,observed_sessions:0};
    const counts={positive:1,negative:0,known:1,unknown:0,excused:0,rate:100};
    const m={observed_events:1,observed_sessions:1,attendance:counts};
    body.published_events=2;
    body.coverage={events_with_sessions:2,events_without_sessions:0};
    body.players=[{fid:"overview-review",nickname:"Overview Scout",group_status:"active",primary_alliance_id:body.alliance_id,avatar_url:"https://gof-formal-avatar.akamaized.net/overview-review.png",metrics:{bear_trap:m,alliance_championship:blank,alliance_mobilization:blank,foundry:blank,canyon:blank}}];
    body.events=[{id:"overview-bear",event_type:"bear_trap",occurred_on:"2026-11-24",recorded_players:1,unknown_home_players:0,metrics:m,session_count:1,activity_cells:{"overview-review":"positive"}},{id:"overview-champ",event_type:"alliance_championship",occurred_on:"2026-11-25",recorded_players:0,unknown_home_players:0,metrics:blank,session_count:1,activity_cells:{}}];
    await route.fulfill({response,json:body});
  });
  await page.route("https://gof-formal-avatar.akamaized.net/overview-review.png",route=>route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII=","base64")}));
  await page.route("**/api/v1/groups/*/players/overview-review",route=>route.fulfill({json:{fid:"overview-review",nickname:"Overview Scout",power:123456}}));
  await page.route("**/api/v1/groups/*/players/overview-review/activity?*",route=>route.fulfill({json:{players:[],events:[]}}));
  await page.reload();
  const eventType=page.locator(".analytics-panel").getByRole("combobox",{name:"Event type",exact:true});
  await expect(eventType).toHaveValue("overall");
  await expect(page.getByRole("heading",{name:"Overall activity",exact:true})).toBeVisible();
  const heatmap=page.locator(".analytics-heatmap");
  await expect(heatmap.getByRole("columnheader")).toHaveCount(4);
  await expect(heatmap.getByRole("columnheader",{name:/Bear Hunt/})).toBeVisible();
  await expect(heatmap.getByRole("columnheader",{name:/Championship/})).toBeVisible();
  const overviewScout=heatmap.getByRole("button",{name:"Overview Scout",exact:true});
  await overviewScout.scrollIntoViewIfNeeded();
  await expect.poll(()=>overviewScout.locator("img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
  await page.getByLabel("Find player").fill("Overview Scout");
  await overviewScout.click();
  const overviewDialog=page.getByRole("dialog",{name:"Player quick view"});
  await expect(overviewDialog).toBeVisible();
  await expect(overviewDialog.getByRole("heading",{name:"Overview Scout"})).toBeVisible();
  await expect(page).toHaveURL(/\/$/);
  await page.keyboard.press("Escape");
  await expect(overviewDialog).toHaveCount(0);
  await expect(overviewScout).toBeFocused();
  await expect(page.getByLabel("Find player")).toHaveValue("Overview Scout");
  await eventType.selectOption("bear_trap");
  await expect(page.getByRole("heading",{name:"Bear Hunt trend"})).toBeVisible();
  await expect(heatmap.getByRole("columnheader")).toHaveCount(2);
  await eventType.selectOption("overall");
  await expect(heatmap.getByRole("columnheader")).toHaveCount(4);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("overview-overall.png"),fullPage:true});
  await page.unroute("**/api/v1/groups/*/analytics?*");
  await page.unroute("**/api/v1/groups/*/players/overview-review");
  await page.unroute("**/api/v1/groups/*/players/overview-review/activity?*");
  await page.unroute("https://gof-formal-avatar.akamaized.net/overview-review.png");
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
  await expect.poll(() => row.locator(".furnace-level img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
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
  await expect(page.locator(".group-sync-card")).toHaveCount(2);
  await expect(page.locator(".group-sync-card").first().getByRole("button",{name:"Sync now"})).toBeVisible();
  expect(await page.locator(".group-sync-card").first().evaluate(el=>{
    const style=getComputedStyle(el);
    return parseFloat(style.paddingLeft)>=12&&parseFloat(style.paddingRight)>=12;
  })).toBe(true);
  expect(await page.locator(".group-sync-card").evaluateAll(cards=>cards[1].getBoundingClientRect().top-cards[0].getBoundingClientRect().bottom)).toBeGreaterThanOrEqual(10);
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("group-management.png"), fullPage: true });

  // Calendar uses real API responses, not fixture data embedded in the page.
  await page.goto("/calendar");
  await expect(page.getByRole("heading",{name:"Event Calendar",exact:true})).toBeVisible();
  const defaultCalendarView=testInfo.project.name==="mobile-390"?"Agenda":"Week";
  await expect(page.getByRole("button",{name:defaultCalendarView,exact:true})).toHaveAttribute("aria-pressed","true");
  await expect(page.getByRole("region",{name:defaultCalendarView+" schedule",exact:true})).toBeVisible();
  const currentGroupId=await page.getByRole("combobox",{name:"Current group",exact:true}).inputValue();
  const currentAllianceId=await page.getByRole("combobox",{name:"Current alliance",exact:true}).inputValue();
  await page.route("**/api/v1/groups/*/calendar?*",async route=>{
    const response=await route.fetch();
    expect(response.ok()).toBe(true);
    const start=new URL(route.request().url()).searchParams.get("start")!;
    const common={group_id:currentGroupId,series_id:null,sequence:0,state_id:"1002",ends_at:null,source:"manual",revision:1};
    await route.fulfill({response,json:{items:[
      {...common,id:"calendar-bear",event_type:"bear_trap",scope:"alliance",alliance_id:currentAllianceId,starts_at:start+"T15:00Z",precision:"minute",phase:"Trap 1",confidence:"confirmed",schedule_status:"scheduled"},
      {...common,id:"calendar-state",event_type:"svs_preparation",scope:"state",alliance_id:null,starts_at:start,precision:"date",phase:"Day 1",confidence:"estimated",schedule_status:"scheduled"},
      {...common,id:"calendar-cancelled",event_type:"foundry",scope:"alliance",alliance_id:currentAllianceId,starts_at:start+"T20:00Z",precision:"minute",phase:"Legion 1",confidence:"confirmed",schedule_status:"cancelled"}
    ]}});
  });
  await page.reload();
  const calendar=page.locator(".calendar-page");
  await calendar.getByRole("button",{name:"Game event catalog",exact:true}).click();
  const catalog=calendar.getByRole("region",{name:"Game event catalog"});
  await expect(catalog).toContainText("65 of 65 events");
  await catalog.getByLabel("Find game event").fill("canyon");
  await catalog.getByRole("button",{name:/Canyon Clash/}).click();
  await expect(catalog).toContainText("Voting");
  await expect(catalog).toContainText("Not a confirmed state schedule");
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await catalog.getByRole("button",{name:"Close catalog"}).click();
  await expect(calendar.getByRole("button",{name:/Bear Trap.*15:00 UTC/})).toBeVisible();
  await expect(calendar.getByRole("button",{name:/SvS Preparation.*Time not set/})).toBeVisible();
  await expect(calendar.getByRole("button",{name:/Foundry Battle/})).toHaveCount(0);
  await expect.poll(()=>calendar.getByRole("button",{name:/Bear Trap/}).locator("img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
  await calendar.getByLabel("Scope").selectOption("state");
  await expect(calendar.getByRole("button",{name:/Bear Trap/})).toHaveCount(0);
  await expect(calendar.getByRole("button",{name:/SvS Preparation/})).toBeVisible();
  await calendar.getByLabel("Scope").selectOption("all");
  await calendar.getByLabel("Show cancelled").check();
  await expect(calendar.getByRole("button",{name:/Foundry Battle.*Cancelled/})).toBeVisible();
  await calendar.getByRole("button",{name:/Bear Trap/}).click();
  await expect(calendar.getByRole("region",{name:"Schedule details"})).toContainText("Manual schedule");
  await calendar.getByRole("button",{name:"Close details"}).click();
  for(const mode of ["Agenda","Week","Month"]){
    await calendar.getByRole("button",{name:mode,exact:true}).click();
    await expect(calendar.getByRole("region",{name:mode+" schedule",exact:true})).toBeVisible();
    await expect(calendar.getByRole("button",{name:/Bear Trap/})).toBeVisible();
    await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
    await page.screenshot({path:testInfo.outputPath("calendar-"+mode.toLowerCase()+".png"),fullPage:true});
  }
  await calendar.getByRole("button",{name:"Next period"}).click();
  await expect(calendar.getByRole("button",{name:/Bear Trap/})).toBeVisible();
  await calendar.getByRole("button",{name:"Today",exact:true}).click();
  await expect(calendar.getByRole("button",{name:/Bear Trap/})).toBeVisible();
  await page.unroute("**/api/v1/groups/*/calendar?*");
  await calendar.getByRole("button",{name:"Add scheduled event",exact:true}).click();
  const scheduleEditor=calendar.getByRole("region",{name:"Schedule editor"});
  await expect(scheduleEditor).toBeVisible();
  await scheduleEditor.getByLabel("Event type").selectOption("foundry");
  await scheduleEditor.getByRole("button",{name:"Use game repeat rule"}).click();
  await expect(scheduleEditor.getByLabel("Repeat every (days)")).toHaveValue("14");
  await expect(scheduleEditor.getByRole("button",{name:"Save schedule"})).toBeDisabled();
  await scheduleEditor.getByRole("checkbox",{name:"I reviewed these dates and confirmed the local repeat pattern"}).check();
  await expect(scheduleEditor.getByRole("button",{name:"Save schedule"})).toBeEnabled();
  await scheduleEditor.getByLabel("Occurrences (including first)").fill("3");
  await expect(scheduleEditor.getByRole("button",{name:"Save schedule"})).toBeDisabled();
  await expect(scheduleEditor.getByLabel("Repeat every (days)")).toBeVisible();
  await scheduleEditor.getByLabel("Precision").selectOption("minute");
  await expect(scheduleEditor.getByLabel("Starts (UTC)",{exact:true})).toHaveAttribute("type","datetime-local");
  await expect(scheduleEditor.getByLabel("Starts (UTC)",{exact:true})).toHaveValue("");
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await scheduleEditor.getByRole("button",{name:"Close editor"}).click();
  await expect(scheduleEditor).toHaveCount(0);

  // Real write/read/edit flow, isolated to one viewport and a distant date.
  if(testInfo.project.name==="desktop-1440"){
    await calendar.getByRole("button",{name:"Add scheduled event",exact:true}).click();
    await scheduleEditor.getByLabel("Event type").selectOption("game:lucky-wheel");
    await scheduleEditor.getByLabel("Starts (UTC)",{exact:true}).fill("2091-02-03");
    const verificationPhase="Verification "+Date.now();
    await scheduleEditor.getByLabel("Phase (optional)").fill(verificationPhase);
    const created=page.waitForResponse(r=>r.request().method()==="POST"&&r.url().endsWith("/calendar"));
    await scheduleEditor.getByRole("button",{name:"Save schedule"}).click();
    expect((await created).status()).toBe(201);
    await expect(scheduleEditor).toHaveCount(0);
    const entry=calendar.getByRole("button",{name:new RegExp("Lucky Wheel.*"+verificationPhase+".*Confirmed")});
    await expect(entry).toBeVisible();
    await entry.click();
    await calendar.getByRole("button",{name:"Edit schedule",exact:true}).click();
    await scheduleEditor.getByLabel("Schedule status").selectOption("cancelled");
    const updated=page.waitForResponse(r=>r.request().method()==="PUT"&&r.url().includes("/calendar/"));
    await scheduleEditor.getByRole("button",{name:"Save schedule"}).click();
    expect((await updated).status()).toBe(200);
    await expect(scheduleEditor).toHaveCount(0);
    await calendar.getByLabel("Show cancelled").check();
    await expect(calendar.getByRole("button",{name:new RegExp("Lucky Wheel.*"+verificationPhase+".*Cancelled")})).toBeVisible();
  }


  // Verify Overall default, low-score sorting, missing evidence and responsive table.
  await page.route("**/api/v1/groups/*/analytics?*",async route=>{
    const response=await route.fetch();
    const body=await response.json();
    const blank={observed_events:0,observed_sessions:0};
    const counts=(positive:number,negative:number)=>({positive,negative,unknown:0,excused:0,known:positive+negative,rate:positive+negative?100*positive/(positive+negative):null});
    body.players=["Review Low","Review High","Review Unknown"].map((nickname,i)=>({fid:"screen-"+i,nickname,avatar_url:i===0?"https://gof-formal-avatar.akamaized.net/quick-view-test.png":null,group_status:"active",primary_alliance_id:body.alliance_id,metrics:{bear_trap:i===2?blank:{observed_events:1,observed_sessions:1,attendance:counts(i,1-i)},alliance_championship:blank,alliance_mobilization:blank,foundry:blank,canyon:blank}}));
    body.published_events=1;body.coverage={events_with_sessions:1,events_without_sessions:0};
    body.events=[{id:"screen-event",event_type:"bear_trap",occurred_on:"2026-11-24",recorded_players:2,unknown_home_players:0,session_count:1,metrics:blank,activity_cells:{"screen-0":"negative","screen-1":"positive"}}];
    await route.fulfill({response,json:body});
  });
  await page.route("https://gof-formal-avatar.akamaized.net/quick-view-test.png",route=>route.fulfill({contentType:"image/png",body:Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aJ1sAAAAASUVORK5CYII=","base64")}));
  await page.route("**/api/v1/groups/*/players/screen-0",route=>route.fulfill({json:{fid:"screen-0",nickname:"Review Low",power:123456,avatar_url:"https://gof-formal-avatar.akamaized.net/quick-view-test.png"}}));
  await page.route("**/api/v1/groups/*/players/screen-0/activity?*",route=>route.fulfill({json:{players:[],events:[]}}));
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
  const low=overallTable.getByRole("button",{name:"Review Low",exact:true});
  await expect.poll(()=>low.locator("img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
  await low.click();
  const quickView=page.getByRole("dialog",{name:"Player quick view"});
  await expect(quickView).toBeVisible();
  await expect(quickView.getByRole("heading",{name:"Review Low"})).toBeVisible();
  await expect(quickView.getByRole("heading",{name:"Game profile"})).toBeVisible();
  await expect(quickView.getByRole("heading",{name:"Event activity"})).toBeVisible();
  await expect(page).toHaveURL(/\/rankings$/);
  await page.screenshot({path:testInfo.outputPath("player-quick-view.png"),fullPage:true});
  await page.keyboard.press("Escape");
  await expect(quickView).toHaveCount(0);
  await expect(low).toBeFocused();
  await expect(page.getByLabel("Find player")).toHaveValue("Review Low");
  await low.click();
  await quickView.getByRole("button",{name:"Close player quick view"}).click();
  await expect(quickView).toHaveCount(0);
  await page.getByLabel("Find player").clear();
  await expect(overallTable.locator("tr").first()).toContainText("Review High");
  await expect(overallTable.getByRole("button",{name:"Review Unknown"}).locator("svg")).toBeVisible();
  await page.goto("/activity");
  await expect(page.getByRole("heading",{name:"Player activity",exact:true})).toBeVisible();
  await page.getByLabel("Find player").fill("Review Low");
  const activityLow=page.getByRole("button",{name:"Review Low",exact:true});
  await expect.poll(()=>activityLow.locator("img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
  await activityLow.click();
  await expect(quickView).toBeVisible();
  await expect(quickView.getByRole("heading",{name:"Overall activity",exact:true})).toBeVisible();
  await expect(page).toHaveURL(/\/activity$/);
  await page.keyboard.press("Escape");
  await expect(quickView).toHaveCount(0);
  await expect(activityLow).toBeFocused();
  await expect(page.getByLabel("Find player")).toHaveValue("Review Low");
  await page.goto("/rankings");
  await expect(page.getByRole("button",{name:"Overall",exact:true})).toHaveAttribute("aria-pressed","true");
  await page.unroute("**/api/v1/groups/*/players/screen-0");
  await page.unroute("**/api/v1/groups/*/players/screen-0/activity?*");
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath("overall-ranking.png"),fullPage:true});
  await page.getByRole("button",{name:"Attendance",exact:true}).click();
  await expect(page.getByLabel("Event / metric")).toBeVisible();
  for(const category of ["Attendance","Contribution"]){
    await page.getByRole("button",{name:category,exact:true}).click();
    if(category==="Contribution")await page.getByLabel("Event / metric").selectOption("bear_damage");
    const table=page.locator(".rankings-panel tbody");
    await expect.poll(()=>table.getByRole("button",{name:"Review Low",exact:true}).locator(".roster-avatar img").evaluate((img:HTMLImageElement)=>img.complete&&img.naturalWidth>0)).toBe(true);
    await expect(table.getByRole("button",{name:"Review Unknown",exact:true}).locator(".roster-avatar svg")).toBeVisible();
  }
  await page.unroute("https://gof-formal-avatar.akamaized.net/quick-view-test.png");
  await page.unroute("**/api/v1/groups/*/analytics?*");

  await page.goto("/admin?mode=events");
  await page.getByLabel(/^Event type/).selectOption("foundry");
  await page.getByLabel(/^Event date/).fill("2026-11-24");
  await page.getByRole("button", { name: "Import historical event",exact:true }).click();
  await expect(page.getByText("Event record created for the selected alliance.")).toBeVisible();
  await page.goto("/events");
  await expect(page.getByRole("heading",{name:"Event history",exact:true})).toBeVisible();
  await page.getByLabel("Record status").selectOption("draft");
  await page.getByLabel("Event type",{exact:true}).selectOption("foundry");
  await page.getByLabel("Find record").fill("2026-11-24");
  await expect(page.getByRole("button",{name:"Foundry Battle",exact:true}).first()).toBeVisible();
  await page.getByLabel("Find record").fill("nonexistent-history-record");
  await expect(page.locator("main .empty-state").getByText("No matching records",{exact:true})).toBeVisible();
  await expect(page.getByRole("button",{name:"Foundry Battle",exact:true})).toHaveCount(0);
  await page.getByRole("button",{name:"Clear filters",exact:true}).click();
  await expect(page.getByRole("button",{name:"Foundry Battle",exact:true}).first()).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await page.getByRole("button",{name:"Open calendar",exact:true}).click();
  await expect(page).toHaveURL(/\/calendar$/);
  await page.locator("main").getByRole("button",{name:"Event history",exact:true}).click();
  await expect(page).toHaveURL(/\/events$/);
  const foundryEvent = page.getByRole("button", {name:"Foundry Battle",exact:true}).first();
  await expect.poll(() => foundryEvent.locator(".event-icon img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await foundryEvent.click();
  await expect.poll(() => page.locator(".event-header__type .event-icon img").evaluate((img: HTMLImageElement) => img.complete && img.naturalWidth > 0)).toBe(true);
  await expect(page.getByRole("heading",{name:"Manual results"})).toBeVisible();
  await expect(page.getByLabel("Legion number")).toHaveValue("legion_1");
  await page.getByRole("button",{name:"Add Legion 1",exact:true}).click();
  await expect(page.getByRole("group",{name:"Existing sessions"}).getByRole("button",{name:"Legion 1 · Registration pending",exact:true})).toHaveAttribute("aria-pressed","true");
  await expect(page.getByLabel("Legion number")).toHaveCount(0);
  await page.getByRole("button",{name:"Add legion",exact:true}).click();
  await expect(page.getByLabel("Legion number")).toHaveValue("legion_2");
  await page.getByRole("button",{name:"Cancel new session"}).click();
  await expect(page.getByLabel("Legion number")).toHaveCount(0);
  await page.route("**/api/v1/ocr/status", route=>route.fulfill({json:{configured:true,provider:"google_vision",max_image_bytes:921600}}));
  await page.route("**/ocr/preview", async route=>{
    expect(route.request().headers()["content-type"]).toBe("image/png");
    expect(route.request().headers()["x-csrf-token"]).toBeTruthy();
    await route.fulfill({json:{provider:"google_vision",text:"Roster Scout 4500000000",tokens:[],warnings:[]}});
  });
  await page.reload();
  const registrationImport=page.getByRole("region",{name:"Registration import"});
  await expect(registrationImport.getByRole("button",{name:"Upload registration screenshots"})).toBeVisible();
  await expect(registrationImport.getByText("No screenshots selected",{exact:true})).toBeVisible();
  const chooserPromise=page.waitForEvent("filechooser");
  await registrationImport.getByRole("button",{name:"Upload registration screenshots"}).click();
  const chooser=await chooserPromise;
  await chooser.setFiles([{name:"first.png",mimeType:"image/png",buffer:Buffer.from("image1")},{name:"second.png",mimeType:"image/png",buffer:Buffer.from("image2")}]);
  await expect(registrationImport.getByText("2 screenshots selected",{exact:true})).toBeVisible();
  await page.getByRole("button",{name:"Battle results",exact:true}).click();
  const resultsImport=page.getByRole("region",{name:"Battle results import"});
  await expect(resultsImport.getByRole("button",{name:"Upload battle result screenshots"})).toBeVisible();
  await expect(registrationImport).toBeHidden();
  await page.getByRole("button",{name:"Registration",exact:true}).click();
  await expect(registrationImport.getByText("2 screenshots selected",{exact:true})).toBeVisible();
  await expect.poll(()=>page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1)).toBe(true);
  await registrationImport.getByRole("button",{name:"Recognize screenshots"}).click();
  await expect(registrationImport.getByText("2 of 2 screenshots recognized")).toBeVisible();
  await expect(page.getByLabel("Roster Scout Personal points")).toHaveCount(0);
  await registrationImport.getByRole("button",{name:"Clear screenshots"}).click();
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
