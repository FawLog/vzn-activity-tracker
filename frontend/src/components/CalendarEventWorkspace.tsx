import {useEffect,useState} from "react";
import {api} from "../lib/api";
import type {EventRecord} from "../lib/types";
import {ManualEventEditor,supportsManualEditor} from "./ManualEventEditor";

export function CalendarEventWorkspace({groupId,eventId,sessionId,onRefresh,onEditingChange}:{groupId:string;eventId:string;sessionId?:string|null;onRefresh:()=>void;onEditingChange:(blocked:boolean)=>void}){
  const [record,setRecord]=useState<EventRecord|null>(null);
  const [error,setError]=useState("");
  const [version,setVersion]=useState(0);
  const [busy,setBusy]=useState(false);
  useEffect(()=>{
    let live=true;
    api.event(groupId,eventId).then(r=>{if(live)setRecord(r)}).catch(e=>{if(live)setError(e.message)});
    return()=>{live=false};
  },[groupId,eventId,version]);
  async function reopen(){
    if(!window.confirm("Reopen published event for corrections?"))return;
    setBusy(true);onEditingChange(true);setError("");
    try{await api.manageEvent(groupId,eventId,{action:"reopen",confirmed:true});setRecord(null);setVersion(v=>v+1);onRefresh();}
    catch(e){setError(e instanceof Error?e.message:"Unable to reopen event");}
    finally{setBusy(false);onEditingChange(false);}
  }
  return <section className="calendar-workspace" aria-label="Calendar event workspace">
    {error&&<p role="alert">{error}</p>}
    {!record&&!error&&<p>Loading event workspace…</p>}
    {record&&supportsManualEditor(record.event_type)&&<>
      {record.status==="published"&&<button className="button button--secondary" disabled={busy} onClick={()=>void reopen()}>Reopen for corrections</button>}
      <ManualEventEditor key={eventId+":"+version} groupId={groupId} record={record} initialSessionId={sessionId??undefined} calendarMode onEditingChange={onEditingChange} onSaved={onRefresh} onPublished={()=>{setRecord(r=>r?{...r,status:"published"}:r);onRefresh();}}/>
    </>}
  </section>;
}
