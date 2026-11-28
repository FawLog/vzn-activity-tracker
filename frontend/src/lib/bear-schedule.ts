import {addDays} from "./calendar";
export type BearSlot={alliance_id:string;time:string;nextDay:boolean};
export type BearSchedulePayload={cycle_date:string;interval_minutes:number;traps:{alliance_id:string;starts_at:string}[];rolling:boolean;confirmed:true;request_key:string};
export function bearSchedulePlan(day:string,hours:number,slots:BearSlot[],rolling:boolean){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(day)||!Number.isFinite(Date.parse(day+"T00:00Z"))||new Date(day+"T00:00Z").toISOString().slice(0,10)!==day||Number(day.slice(0,4))<2000||Number(day.slice(0,4))>2099)throw Error("Choose a valid first cycle date.");
  const interval=hours*60;
  if(!Number.isInteger(interval)||interval<2850||interval>10080)throw Error("Repeat interval must be 47.5–168 hours.");
  if(!slots.length||slots.length>30||slots.some(s=>!s.alliance_id||!/^([01]\d|2[0-3]):[0-5]\d$/.test(s.time)))throw Error("Choose an alliance and UTC time for every trap.");
  if(slots.every(s=>s.nextDay))throw Error("At least one trap must start on the first cycle date.");
  const traps=slots.map(s=>({alliance_id:s.alliance_id,starts_at:(s.nextDay?addDays(day,1):day)+"T"+s.time+"Z"}));
  if(new Set(traps.map(s=>s.alliance_id+"|"+s.starts_at)).size!==traps.length)throw Error("Two traps have the same alliance and start time.");
  const anchor=Math.min(...traps.map(s=>Date.parse(s.starts_at)));
  if(traps.some(s=>Date.parse(s.starts_at)-anchor>=interval*60000))throw Error("All traps must start within the first shared cycle.");
  const count=rolling?Math.min(60,1+Math.floor(60*1440/interval)):4;
  const format=(ms:number)=>{
    const date=new Date(ms);
    if(date.getUTCFullYear()>2099)throw Error("Schedule exceeds supported dates.");
    return date.toISOString().slice(0,16)+"Z";
  };
  const cycles=Array.from({length:Math.min(count,3)},(_,i)=>({date:format(anchor+i*interval*60000).slice(0,10),
    traps:traps.map((s,j)=>({number:j+1,alliance_id:s.alliance_id,start:format(Date.parse(s.starts_at)+i*interval*60000)}))}));
  // Validate the last end as well as the first visible preview.
  traps.forEach(s=>format(Date.parse(s.starts_at)+((count-1)*interval+30)*60000));
  return {payload:{cycle_date:day,interval_minutes:interval,traps,rolling,confirmed:true as const},count,cycles};
}
