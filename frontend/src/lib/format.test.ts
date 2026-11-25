import { describe, expect, it } from "vitest";
import { eventLabel, formatDate, formatFurnaceLevel, formatAllianceRank } from "./format";

describe("record formatting", () => {
  it("keeps event units identifiable by their own names", () => {
    expect(eventLabel("svs_preparation")).toBe("SvS Preparation");
    expect(eventLabel("alliance_showdown")).toBe("Alliance Showdown");
  });

  it("formats an event date without applying the browser timezone", () => {
    expect(formatDate("2026-11-24")).toContain("2026");
  });
});

describe("roster formatting", () => {
  it("maps every crystal furnace milestone and intermediate step", () => {
    for (let level = 1; level <= 30; level++) expect(formatFurnaceLevel(level)).toBe(String(level));
    for (let step = 1; step <= 4; step++) expect(formatFurnaceLevel(30 + step)).toBe(`30-${step}`);
    for (let fc = 1; fc <= 10; fc++) {
      expect(formatFurnaceLevel(30 + 5 * fc)).toBe(`FC${fc}`);
      if (fc < 10) for (let step = 1; step <= 4; step++) expect(formatFurnaceLevel(30 + 5 * fc + step)).toBe(`FC${fc}-${step}`);
    }
    expect(formatFurnaceLevel(null)).toBe("—");
    expect(formatFurnaceLevel(0)).toBe("—");
    expect(formatFurnaceLevel(81)).toBe("81");
  });
  it("normalizes known alliance ranks without inventing missing ones", () => {
    for (let rank = 1; rank <= 5; rank++) {
      expect(formatAllianceRank(rank)).toBe(`R${rank}`);
      expect(formatAllianceRank(`r${rank}`)).toBe(`R${rank}`);
      expect(formatAllianceRank(String(rank))).toBe(`R${rank}`);
    }
    expect(formatAllianceRank(null)).toBe("—");
    expect(formatAllianceRank("R0")).toBe("—");
    expect(formatAllianceRank("unknown")).toBe("—");
  });
});
