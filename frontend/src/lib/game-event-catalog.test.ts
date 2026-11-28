import { describe, expect, it } from "vitest";
import { catalogVersion, gameEvents, gameEventForCalendar, repeatLabel, searchGameEvents } from "./game-event-catalog";

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
    expect(svs.schedule?.runs).toContainEqual({label:"Battle",length:12,unit:"hours",startWeekday:"saturday",startTimeUtc:"10:00"});
    expect(gameEventForCalendar("unknown")).toBeUndefined();
  });
  it("searches without creating or changing calendar events",()=>{
    expect(searchGameEvents("  canyon ").map(e=>e.id)).toEqual(["canyon-clash"]);
    expect(searchGameEvents("canyon","solo")).toEqual([]);
    expect(repeatLabel(undefined)).toBe("Repeat rule unavailable");
  });
});
