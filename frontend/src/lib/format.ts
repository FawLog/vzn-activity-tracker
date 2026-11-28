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
  return value==="svs_matchmaking"?"SvS Matchmaking":value==="svs_triage"?"SvS Field Triage":eventTypeLabels[value] ?? value.replaceAll("_", " ");
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
  const date = new Date(timestampMillis(value));
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

// Provider timestamps may be ISO offsets or SQLite UTC timestamps.
function timestampMillis(value:string|null|undefined):number {
  if(!value)return NaN;
  const iso=value.replace(" ","T");
  return Date.parse(/(?:Z|[+-][0-9]{2}:[0-9]{2})$/i.test(iso)?iso:iso+"Z");
}
export function shortElapsed(from:string|null|undefined,to:number=Date.now()):string|null {
  const elapsed=to-timestampMillis(from);
  if(!Number.isFinite(elapsed)||elapsed<0)return null;
  const minutes=Math.floor(elapsed/60000);
  return minutes<1?"<1m":minutes<60?minutes+"m":Math.floor(minutes/60)+"h";
}
export function observationInterval(previous:string|null|undefined,current:string|null|undefined):string|null {
  return shortElapsed(previous,timestampMillis(current));
}
