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
