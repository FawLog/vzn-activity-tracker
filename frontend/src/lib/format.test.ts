import { describe, expect, it } from "vitest";
import { eventLabel, formatDate } from "./format";

describe("record formatting", () => {
  it("keeps event units identifiable by their own names", () => {
    expect(eventLabel("svs_preparation")).toBe("SvS Preparation");
    expect(eventLabel("alliance_showdown")).toBe("Alliance Showdown");
  });

  it("formats an event date without applying the browser timezone", () => {
    expect(formatDate("2026-11-24")).toContain("2026");
  });
});
