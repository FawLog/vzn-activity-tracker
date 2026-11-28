// Build-time projection of the pinned package; no package-root import in the browser.
import { createRequire } from "node:module";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import type { Plugin } from "vite";

const require = createRequire(import.meta.url);
const version = "0.11.0";
// Exact membership of events() in the upstream v0.11.0 registry, not a second copy of event data.
const files = [
  "alliance-championship.json",
  "alliance-mobilization.json",
  "alliance-showdown.json",
  "armament-competition.json",
  "bear-hunt.json",
  "beast-whisperer.json",
  "brothers-in-arms.json",
  "canyon-clash.json",
  "city-development.json",
  "crazy-joe.json",
  "crystal-reactivation-2.json",
  "deadshot.json",
  "defeat-nearby-beasts.json",
  "develop-new-tech-2.json",
  "develop-new-tech.json",
  "dreamscape-memory.json",
  "fishing-tournament.json",
  "flame-and-fang.json",
  "foundry-battle.json",
  "frostdragon-tyrant.json",
  "frostfire-mine.json",
  "frosty-fortune-skin-event.json",
  "ginas-revenge.json",
  "grow-your-heroes.json",
  "hall-of-chief.json",
  "hall-of-heroes.json",
  "hero-rally.json",
  "heros-mission.json",
  "home-beyond.json",
  "icefire-warhymn-league.json",
  "journey-of-light.json",
  "king-of-icefield.json",
  "lucky-wheel.json",
  "mercenary-prestige.json",
  "mia-fortune.json",
  "officer-project.json",
  "plan-your-city.json",
  "power-up.json",
  "return-to-tundra.json",
  "romance-season.json",
  "shining-city-pack.json",
  "silver-shell-events.json",
  "snowbusters.json",
  "stand-of-arms.json",
  "state-merger.json",
  "state-transfer-event.json",
  "sunfire-castle.json",
  "svs-state-of-power.json",
  "symphony-of-change.json",
  "the-labyrinth.json",
  "treasure-hunter.json",
  "trial-event.json",
  "trusted-chief.json",
  "tundra-adventure.json",
  "tundra-album-2.json",
  "tundra-arms-league.json",
  "tundra-games.json",
  "tundra-star.json",
  "tundra-trade-route.json",
  "tundra-trading-station-guide.json",
  "vault-of-enigma.json",
  "vision-of-dawn.json",
  "war-preparation.json",
  "wild-brawl.json",
  "working-overtime-2.json"
];
const virtualId = "virtual:wos-event-catalog";
export function eventCatalogPlugin(): Plugin {
  return {
    name: "vzn-event-catalog",
    resolveId(id) { return id === virtualId ? "\0" + id : undefined; },
    load(id) {
      if (id !== "\0" + virtualId) return;
      const directory = dirname(require.resolve("whiteout-survival-data/data/events/bear-hunt.json"));
      const root = join(directory, "../..");
      const manifest = JSON.parse(readFileSync(join(root, "package.json"), "utf8"));
      if (manifest.version !== version) throw new Error("Review event catalog before upgrading whiteout-survival-data");
      const timeline = JSON.parse(readFileSync(join(root, "data/server-timeline.json"), "utf8")) as {day:number;eventIds:string[];heroIds?:string[];petIds?:string[];expertIds?:string[];fireCrystalLevelIds?:string[];unlocks?:{name:string;requirement?:string}[]}[];
      const milestones = timeline.map(m=>{
        if(!Number.isInteger(m.day)||m.day<0)throw Error("Invalid state timeline day");
        return {day:m.day,eventIds:m.eventIds??[],heroIds:m.heroIds??[],petIds:m.petIds??[],expertIds:m.expertIds??[],fireCrystalLevelIds:m.fireCrystalLevelIds??[],unlocks:(m.unlocks??[]).map(u=>({name:u.name,requirement:u.requirement}))};
      }).sort((a,b)=>a.day-b.day);
      const overrides=JSON.parse(readFileSync(new URL("./game-catalog-overrides.json",import.meta.url),"utf8"));
      const imports: string[] = [];
      const rows = files.map((file, index) => {
        const event = JSON.parse(readFileSync(join(directory, file), "utf8"));
        if (typeof event.id !== "string" || typeof event.name !== "string" || typeof event.category !== "string") {
          throw new Error("Invalid game event: " + file);
        }
        let icon = "null";
        if (typeof event.img === "string" && /^\/images\/events\/[a-zA-Z0-9._-]+\.png$/.test(event.img)) {
          const path = join(root, event.img.slice(1));
          if (existsSync(path)) {
            icon = "icon" + index;
            imports.push("import " + icon + " from " + JSON.stringify(path.replaceAll("\\", "/") + "?url") + ";");
          }
        }
        const {id, name, category, description, frequency, duration, requirements} = event;
        const patch=overrides[id];
        const requiredLabels:string[]=patch?.requiredRunLabels??["Voting"];
        const supplement=patch?.runs&&requiredLabels.some(label=>!event.schedule?.runs?.some((run:{label?:string})=>run.label===label))?patch:undefined;
        const repeatSupplement=patch?.repeat&&!event.schedule?.repeat?patch.repeat:undefined;
        const schedule=supplement||repeatSupplement?{...event.schedule,...(supplement?{runs:supplement.runs}:{}),...(repeatSupplement?{repeat:repeatSupplement}:{})}:event.schedule;
        const phases=event.phases??supplement?.phases;
        const scheduleOverride=patch&&(supplement||repeatSupplement||patch.dependency)?{source:patch.source,checkedOn:patch.checkedOn,note:patch.note}:undefined;
        const summary = {id, name, category, description, frequency, duration, schedule, requirements, phases, scheduleOverride,scheduleDependency:patch?.dependency,
          unlockDay: timeline.find(m=>m.eventIds?.includes(id))?.day,
          stages: Array.isArray(event.days) ? event.days.map((d: {day?:unknown;name?:unknown;note?:unknown})=>({
            id: String(d.day??""), name: typeof d.name==="string"?d.name:undefined, note: typeof d.note==="string"?d.note:undefined
          })).filter((d:{id:string})=>d.id) : [],
          details: Object.fromEntries(["days","missions","missionPointsLabel","scoreUnit","tiers","rewards","personalRankings","allianceRankings","allianceRankingUpdates","expertTiers","pointLevels","damageRewards","versions"].filter(key=>event[key]!==undefined).map(key=>[key,event[key]])),
          dayCount: Array.isArray(event.days) ? event.days.length : 0,
          missionCount: Array.isArray(event.missions) ? event.missions.length : 0,
          hasVariants: Array.isArray(event.versions) && event.versions.length > 0};
        return "{..."+JSON.stringify(summary)+",icon:"+icon+"}";
      });
      return imports.join("\n") + "\nexport const catalogVersion = "+JSON.stringify(version)+";\nexport const catalog = ["+rows.join(",")+"];\nexport const stateTimeline = "+JSON.stringify(milestones)+";";
    }
  };
}
