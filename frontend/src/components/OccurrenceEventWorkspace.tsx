import {useEffect,useRef,useState} from "react";
import {api,type OccurrenceWorkspaceState} from "../lib/api";
import {useNavigationGuard} from "../lib/navigation-guard";
import {CalendarEventWorkspace} from "./CalendarEventWorkspace";
import {formatDate} from "../lib/format";

type Props={groupId:string;occurrenceId:string;writable:boolean;blocked:boolean;onEditingChange:(blocked:boolean)=>void;onRefresh:()=>void};
const label=(s:OccurrenceWorkspaceState["slots"][number])=>s.key==="main"?"event data":s.key.replace("_"," ").replace(/^./,c=>c.toUpperCase());

export function OccurrenceEventWorkspace({groupId,occurrenceId,writable,blocked,onEditingChange,onRefresh}:Props){
  const [data,setData]=useState<OccurrenceWorkspaceState|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [refresh,setRefresh]=useState(0);
  const [version,setVersion]=useState(0);
  const [preferred,setPreferred]=useState<string|undefined>();
  const lock=useRef(false);
  useNavigationGuard(false,busy);
  useEffect(()=>{
    const controller=new AbortController();
    api.occurrenceWorkspace(groupId,occurrenceId,controller.signal).then(result=>{
      if(!controller.signal.aborted){setData(result);setPreferred(old=>old??result.slots.find(s=>s.id===occurrenceId)?.session_id??undefined);setError("");}
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[groupId,occurrenceId,refresh]);
  async function start(slot:OccurrenceWorkspaceState["slots"][number]){
    if(lock.current||blocked||!writable)return;
    lock.current=true;setBusy(true);onEditingChange(true);setError("");
    try{
      const result=await api.startOccurrenceWorkspace(groupId,occurrenceId,slot.id,slot.revision);
      setData(result);setPreferred(result.slots.find(s=>s.id===slot.id)?.session_id??undefined);setVersion(n=>n+1);onRefresh();
    }catch(e){setError(e instanceof Error?e.message:"Unable to open event data");}
    finally{lock.current=false;setBusy(false);onEditingChange(false);}
  }
  return <section className="calendar-battle-workspace" aria-label="Shared event data">
    {error&&<p role="alert">{error}</p>}{!data&&!error&&<p>Loading event data…</p>}
    {data&&<><p>{data.kind==="bear_trap"?"Bear cycle":"Event date"}: {formatDate(data.cycle_date)} · UTC{data.event_status?" · "+data.event_status:""}</p>
      {writable&&data.slots.some(s=>!s.linked&&!s.cancelled)&&<div className="calendar-legion-setup">
        {data.slots.filter(s=>!s.linked&&!s.cancelled).map(slot=><div key={slot.id} className="calendar-legion-start">
          {data.kind==="bear_trap"&&<strong>{label(slot)} · {slot.tag}</strong>}
          <span>{formatDate(slot.starts_at)}{slot.precision==="minute"?" · "+slot.starts_at.slice(11,16)+" UTC":""}{slot.confidence==="estimated"?" · Estimated":""}</span>
          <button type="button" className="button button--primary" disabled={busy||blocked||data.event_status==="published"||data.kind==="bear_trap"&&slot.precision!=="minute"} onClick={()=>void start(slot)}>{slot.confidence==="estimated"?"Confirm and open ":data.event_id&&data.kind==="bear_trap"?"Add ":"Open "}{label(slot)}</button>
        </div>)}
        {data.event_status==="published"&&<p>Reopen the event before adding a missing session.</p>}
      </div>}
      {data.event_id&&writable&&<CalendarEventWorkspace key={data.event_id+":"+version} groupId={groupId} eventId={data.event_id} sessionId={preferred} onEditingChange={onEditingChange} onRefresh={()=>{setRefresh(n=>n+1);onRefresh();}}/>}
      {!writable&&<p>This event is read-only.</p>}
    </>}
  </section>;
}
