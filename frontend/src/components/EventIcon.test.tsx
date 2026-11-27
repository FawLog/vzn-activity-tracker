import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { EventIcon } from "./EventIcon";
import { eventIconUrl } from "../lib/eventIcons";

describe("EventIcon", () => {
  it.each([
    ["bear_trap", "bear-hunt"],
    ["foundry", "foundry-battle"],
    ["alliance_championship", "alliance-championship"],
    ["alliance_mobilization", "alliance-mobilization"],
    ["canyon", "canyon-clash"],
    ["alliance_showdown", "alliance-showdown"],
    ["castle_battle", "sunfire-castle"],
    ["svs_preparation", "svs-state-of-power"],
    ["svs_battle", "svs-state-of-power"],
  ])("maps %s to its own game artwork", (type, filename) => {
    expect(eventIconUrl(type)).toContain(filename + ".png");
    const { container } = render(<EventIcon eventType={type} />);
    expect(container.querySelector("img")).toHaveAttribute("src", eventIconUrl(type));
    expect(container.querySelector("img")).toHaveAttribute("alt", "");
    expect(container.firstChild).toHaveAttribute("aria-hidden", "true");
  });

  it("uses a decorative fallback for unknown event types", () => {
    expect(eventIconUrl("constructor")).toBeUndefined();
    const { container } = render(<EventIcon eventType="unknown" />);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("svg")).not.toBeNull();
  });

  it("falls back after an image error and supports a changed event type", () => {
    const { container, rerender } = render(<EventIcon eventType="foundry" />);
    fireEvent.error(container.querySelector("img")!);
    expect(container.querySelector("svg")).not.toBeNull();
    rerender(<EventIcon eventType="bear_trap" />);
    expect(container.querySelector("img")).toHaveAttribute("src", eventIconUrl("bear_trap"));
  });
});
