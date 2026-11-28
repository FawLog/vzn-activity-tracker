import {eventTypeOptions} from "./format";
import {extraCalendarEvents} from "./game-event-catalog";
import type {CycleKind} from "./calendar-cycles";
export const cycleTypes:Record<string,CycleKind>={"cycle:canyon":"canyon","cycle:foundry":"foundry","cycle:svs":"svs"};
export const creationEventOptions:[string,string][]=[
 ["bear:batch","Bear Trap"],["cycle:foundry","Foundry Battle"],["cycle:canyon","Canyon Clash"],["cycle:svs","State of Power (SvS)"],
 ...eventTypeOptions.filter(([v])=>!["bear_trap","foundry","canyon","svs_preparation","svs_battle"].includes(v)),
 ...extraCalendarEvents.map(e=>["game:"+e.id,e.name] as [string,string])
];
export function creationType(type:string):string{
 return ({bear_trap:"bear:batch",foundry:"cycle:foundry",canyon:"cycle:canyon",svs_preparation:"cycle:svs",svs_battle:"cycle:svs"} as Record<string,string>)[type]??type;
}
