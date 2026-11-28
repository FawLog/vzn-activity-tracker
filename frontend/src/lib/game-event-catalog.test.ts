import { describe, expect, it } from "vitest";
import { catalogVersion, gameEvents, gameEventForCalendar, repeatLabel, eventRepeatLabel, searchGameEvents } from "./game-event-catalog";

describe("pinned game catalog",()=>{
  it("imports the upstream event registry and preserves missing schedules",()=>{
    expect(catalogVersion).toBe("0.11.0");
    expect(gameEvents).toHaveLength(65);
    expect(new Set(gameEvents.map(e=>e.id)).size).toBe(65);
    expect(gameEvents.filter(e=>e.schedule)).toHaveLength(50);
    expect(gameEvents.find(e=>e.id==="deadshot")?.schedule).toBeUndefined();
  });
  it("keeps precise cooldown, phased runs and source labels",()=>{
    const bear=gameEventForCalendar("bear_trap")!;
    expect(bear.schedule?.repeat).toEqual({kind:"every",every:47.5,unit:"hours"});
    expect(bear.icon).toBeTruthy();
    expect(repeatLabel(bear.schedule?.repeat)).toBe("Every 47.5 hours");
    const svs=gameEventForCalendar("svs_preparation")!;
    expect(svs).toBe(gameEventForCalendar("svs_battle"));
    expect(svs.dayCount).toBe(6);
    expect(svs.stages.map(s=>s.id)).toEqual(["1","2","3","4","5","Battle"]);
    expect(svs.stages[4].name).toBe("Power Boost");
    expect(svs.schedule?.runs).toContainEqual({label:"Battle",length:12,unit:"hours",startWeekday:"saturday",startTimeUtc:"10:00"});
    expect(gameEventForCalendar("unknown")).toBeUndefined();
  });
  it("searches without creating or changing calendar events",()=>{
    expect(searchGameEvents("  canyon ").map(e=>e.id)).toEqual(["canyon-clash"]);
    expect(searchGameEvents("canyon","solo")).toEqual([]);
    expect(repeatLabel(undefined)).toBe("Repeat rule unavailable");
  });
});

it("supplements Foundry phases without changing upstream cadence",()=>{
 const event=gameEventForCalendar("foundry")!;
 expect(event.schedule?.runs?.map(r=>r.label)).toEqual(["Voting","Registration","Matchmaking","Battle"]);
 expect(event.scheduleOverride?.source).toContain("centurygames.helpshift.com");
 expect(event.schedule?.repeat).toEqual({kind:"every",every:2,unit:"weeks"});
});

it("preserves dependent and irregular source rules instead of guessing fixed intervals",()=>{
 const flame=gameEventForCalendar("game:flame-and-fang")!;
 expect(flame.schedule?.repeat).toEqual(gameEventForCalendar("svs_preparation")?.schedule?.repeat);
 expect(flame.scheduleDependency).toMatchObject({parent:"svs-state-of-power",follow:true});
 expect(eventRepeatLabel(flame)).toContain("SvS preparation");
 const joe=gameEventForCalendar("game:crazy-joe")!;
 expect(joe.schedule?.repeat).toBeUndefined();
 expect(eventRepeatLabel(joe)).toContain("King of Icefield");
 expect(eventRepeatLabel(gameEventForCalendar("game:tundra-games")!)).toBe("Irregular");
 expect(gameEvents.filter(e=>e.schedule?.repeat)).toHaveLength(29);
});

// Reviewed classification of every upstream v0.11.0 event. If the registry changes,
// this must be reviewed rather than filling missing recurrence with arbitrary dates.
it("classifies every source event and only supplements the reviewed Flame cadence",()=>{
 const groups={"fixed":["alliance-championship","alliance-showdown","armament-competition","bear-hunt","canyon-clash","defeat-nearby-beasts","foundry-battle","frostfire-mine","hall-of-chief","hall-of-heroes","heros-mission","icefire-warhymn-league","lucky-wheel","mercenary-prestige","officer-project","sunfire-castle","svs-state-of-power","tundra-trade-route","wild-brawl"],"months":["alliance-mobilization","brothers-in-arms","fishing-tournament","king-of-icefield","mia-fortune","romance-season","snowbusters","tundra-trading-station-guide"],"once":["beast-whisperer"],"linked":["crazy-joe","crystal-reactivation-2","flame-and-fang"],"irregular":["dreamscape-memory","frosty-fortune-skin-event","journey-of-light","shining-city-pack","silver-shell-events","state-merger","state-transfer-event","tundra-adventure","tundra-games"],"conditions":["ginas-revenge","symphony-of-change"],"persistent":["deadshot","the-labyrinth","tundra-album-2"],"unknown":["city-development","develop-new-tech-2","develop-new-tech","frostdragon-tyrant","grow-your-heroes","hero-rally","home-beyond","plan-your-city","power-up","return-to-tundra","stand-of-arms","treasure-hunter","trial-event","trusted-chief","tundra-arms-league","tundra-star","vault-of-enigma","vision-of-dawn","war-preparation","working-overtime-2"]};
 expect(Object.values(groups).flat().sort()).toEqual(gameEvents.map(e=>e.id).sort());
 for(const id of groups.fixed){const e=gameEvents.find(e=>e.id===id)!;expect(e.schedule?.repeat).toMatchObject({kind:"every"});}
 for(const id of groups.months)expect(gameEvents.find(e=>e.id===id)?.schedule?.repeat).toMatchObject({kind:"every",unit:"months"});
 for(const id of groups.once)expect(gameEvents.find(e=>e.id===id)?.schedule?.repeat).toEqual({kind:"none"});
 for(const id of [...groups.linked.filter(id=>id!=="flame-and-fang"),...groups.irregular,...groups.conditions,...groups.persistent,...groups.unknown])expect(gameEvents.find(e=>e.id===id)?.schedule?.repeat).toBeUndefined();
});

it("adds all four SvS runs to the same catalog reference",()=>{
 const svs=gameEventForCalendar("svs_preparation")!;
 expect(gameEventForCalendar("svs_matchmaking")).toBe(svs);
 expect(gameEventForCalendar("svs_triage")).toBe(svs);
 expect(svs.schedule?.runs?.map(r=>r.label)).toEqual(["Matchmaking","Preparation","Battle","Field Triage"]);
 expect(svs.scheduleOverride?.note).toContain("estimated");
});
