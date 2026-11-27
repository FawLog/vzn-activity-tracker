// Only these five assets enter the frontend build; never import the package root.
// Source: whiteout-survival-data@0.11.0. Game artwork remains its respective owner's property.
import bear from "whiteout-survival-data/images/events/bear-hunt.png";
import foundry from "whiteout-survival-data/images/events/foundry-battle.png";
import championship from "whiteout-survival-data/images/events/alliance-championship.png";
import mobilization from "whiteout-survival-data/images/events/alliance-mobilization.png";
import canyon from "whiteout-survival-data/images/events/canyon-clash.png";

const icons = new Map<string, string>([
  ["bear_trap", bear],
  ["foundry", foundry],
  ["alliance_championship", championship],
  ["alliance_mobilization", mobilization],
  ["canyon", canyon],
]);

export function eventIconUrl(eventType: string): string | undefined {
  return icons.get(eventType);
}
