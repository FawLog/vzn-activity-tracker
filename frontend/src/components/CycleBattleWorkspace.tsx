import {useEffect,useRef,useState} from "react";
import {api,type CycleWorkspaceState} from "../lib/api";
import {allowNavigation,useNavigationGuard} from "../lib/navigation-guard";
import {CalendarEventWorkspace} from "./CalendarEventWorkspace";
import {formatDate} from "../lib/format";

type Props={groupId:string;cycleId:string;writable:boolean;blocked:boolean;onEditingChange:(blocked:boolean)=>void;onRefresh:()=>void};
type Legion="legion_1"|"legion_2";
const title=(key:Legion)=>"Legion "+key.slice(-1);

export function CycleBattleWorkspace({groupId,cycleId,writable,blocked,onEditingChange,onRefresh}:Props){
  const [data,setData]=useState<CycleWorkspaceState|null>(null);
  const [times,setTimes]=useState<Partial<Record<Legion,string>>>({});
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const [version,setVersion]=useState(0);
  const [preferred,setPreferred]=useState<string|undefined>();
  const lock=useRef(false);
  const [refresh,setRefresh]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    api.cycleWorkspace(groupId,cycleId,controller.signal).then(result=>{
      if(!controller.signal.aborted){setData(result);setError("");}
    }).catch(e=>{if(!controller.signal.aborted)setError(e.message);});
    return ()=>controller.abort();
  },[groupId,cycleId,refresh]);
  useNavigationGuard(Object.keys(times).length>0,busy);
  async function start(slot:CycleWorkspaceState["slots"][number]){
    if(!data||lock.current||blocked||!writable)return;
    const time=times[slot.key]??slot.starts_at?.slice(11,16)??"";
    if(!/^\d{2}:\d{2}$/.test(time))return;
    lock.current=true;setBusy(true);onEditingChange(true);setError("");
    try{
      const result=await api.startCycleWorkspace(groupId,cycleId,slot.key,data.battle_date+"T"+time+"Z",data.revisions);
      setData(result);setPreferred(result.slots.find(s=>s.key===slot.key)?.session_id??undefined);
      setTimes(old=>{const next={...old};delete next[slot.key];return next;});setVersion(n=>n+1);onRefresh();
    }catch(e){setError(e instanceof Error?e.message:"Unable to open legion");}
    finally{lock.current=false;setBusy(false);onEditingChange(false);}
  }
  const pending=data?.slots.filter(s=>!s.linked&&!s.cancelled)??[];
  return <section aria-label="Battle event data" className="calendar-battle-workspace">
    {!data&&!error&&<p>Loading event data…</p>}{error&&<p role="alert">{error}</p>}
    {data&&<><p>Battle date: {formatDate(data.battle_date)} · UTC{data.event_status?" · "+data.event_status:""}</p>
      {writable&&pending.length>0&&<div className="calendar-legion-setup">
        {!data.event_id&&<p>Choose a legion to enter registration or battle results. Confirm its UTC start time once.</p>}
        {pending.map(slot=><div key={slot.key} className="calendar-legion-start">
          <strong>{title(slot.key)}</strong>
          <label>{title(slot.key)} start (UTC)<input type="time" value={times[slot.key]??slot.starts_at?.slice(11,16)??""} disabled={busy||blocked||!!slot.session_id} onChange={e=>setTimes(old=>({...old,[slot.key]:e.target.value}))}/></label>
          <button type="button" className="button button--primary" disabled={busy||blocked||!(times[slot.key]??slot.starts_at?.slice(11,16))||data.event_status==="published"} onClick={()=>void start(slot)}>{data.event_id?"Add "+title(slot.key):"Open "+title(slot.key)}</button>
        </div>)}
        {data.event_status==="published"&&<p>Reopen the event before adding a missing legion.</p>}
      </div>}
      {data.event_id&&writable&&<CalendarEventWorkspace key={data.event_id+":"+version} groupId={groupId} eventId={data.event_id} sessionId={preferred} onEditingChange={onEditingChange} onRefresh={()=>{setRefresh(n=>n+1);onRefresh();}}/>}
      {!writable&&<p>This event is read-only.</p>}
    </>}
  </section>;
}
