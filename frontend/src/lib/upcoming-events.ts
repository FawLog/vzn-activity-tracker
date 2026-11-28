import {addDays,utcDay,type CalendarOccurrence} from "./calendar";

export function upcomingEvents(rows:CalendarOccurrence[],now:number,groupId:string,allianceIds:ReadonlySet<string>,stateIds:ReadonlySet<string>,days=7){
  const today=utcDay(new Date(now)),end=addDays(today,days);
  return rows.filter(r=>{
    if(r.group_id!==groupId||r.schedule_status!=="scheduled"||r.starts_at.slice(0,10)>=end)return false;
    if(r.scope==="alliance"? !r.alliance_id||!allianceIds.has(r.alliance_id):!stateIds.has(r.state_id))return false;
    if(r.precision==="date")return r.starts_at>=today||!!r.ends_at&&r.ends_at>today;
    return Date.parse(r.starts_at)>=now||!!r.ends_at&&Date.parse(r.ends_at)>now;
  }).sort((a,b)=>{
    const aStarted=a.precision==="date"?a.starts_at<today:Date.parse(a.starts_at)<now;
    const bStarted=b.precision==="date"?b.starts_at<today:Date.parse(b.starts_at)<now;
    return Number(bStarted)-Number(aStarted)||a.starts_at.localeCompare(b.starts_at)||a.id.localeCompare(b.id);
  });
}

export function upcomingTiming(row:CalendarOccurrence,now:number){
  const today=utcDay(new Date(now));
  if(row.precision==="date"){
    if(row.starts_at<today)return "Scheduled date range · time not set";
    if(row.starts_at===today)return "Today · time not set";
    const days=Math.round((Date.parse(row.starts_at)-Date.parse(today))/86400000);
    return "In "+days+"d · time not set";
  }
  const start=Date.parse(row.starts_at);
  if(start<=now)return row.ends_at&&Date.parse(row.ends_at)>now?"Scheduled now":"Scheduled start";
  const minutes=Math.ceil((start-now)/60000);
  if(minutes>=1440)return "In "+Math.floor(minutes/1440)+"d "+Math.floor(minutes%1440/60)+"h";
  if(minutes>=60)return "In "+Math.floor(minutes/60)+"h "+minutes%60+"m";
  return "In "+minutes+"m";
}

export function upcomingCalendarUrl(row:CalendarOccurrence,now:number){
  const today=utcDay(new Date(now));
  return "/calendar?"+new URLSearchParams({day:row.starts_at.slice(0,10)<today?today:row.starts_at.slice(0,10),occurrence:row.id});
}
