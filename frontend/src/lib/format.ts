export const eventTypeLabels: Record<string, string> = {
  svs_preparation: "SvS Preparation",
  alliance_mobilization: "Alliance Mobilization",
  alliance_showdown: "Alliance Showdown",
  foundry: "Foundry Battle",
  canyon: "Canyon Clash",
  bear_trap: "Bear Trap",
  alliance_championship: "Alliance Championship",
  winter_siege: "Winter Siege",
  svs_battle: "SvS Battle",
  castle_battle: "Castle Battle",
  fortress_stronghold: "Fortress / Stronghold",
};

export const eventTypeOptions = Object.entries(eventTypeLabels);

export function eventLabel(value: string): string {
  return eventTypeLabels[value] ?? value.replaceAll("_", " ");
}

export function formatDate(value: string): string {
  const date = new Date(`${value.slice(0, 10)}T00:00:00Z`);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en", {
    year: "numeric",
    month: "short",
    day: "2-digit",
    timeZone: "UTC",
  }).format(date);
}

export function formatTimestamp(value: string): string {
  const normalized = value.endsWith("Z") ? value : `${value.replace(" ", "T")}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.valueOf())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function formatFurnaceLevel(level?: number | null): string {
  if (level == null || !Number.isInteger(level) || level < 1) return "—";
  if (level <= 30 || level > 80) return String(level);
  const crystals = Math.floor((level - 30) / 5);
  const step = (level - 30) % 5;
  const base = crystals === 0 ? "30" : `FC${crystals}`;
  return step === 0 ? base : `${base}-${step}`;
}

export function formatAllianceRank(rank?: string | number | null): string {
  const match = String(rank ?? "").trim().match(/^R?([1-5])$/i);
  return match ? `R${match[1]}` : "—";
}
