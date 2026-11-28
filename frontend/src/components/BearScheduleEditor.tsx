import {useRef,useState,type FormEvent} from "react";
import {Plus,Trash2} from "lucide-react";
import {api} from "../lib/api";
import {bearSchedulePlan,type BearSlot} from "../lib/bear-schedule";
import {utcDay} from "../lib/calendar";
import {eventTypeOptions} from "../lib/format";
import {extraCalendarEvents} from "../lib/game-event-catalog";
import {allowNavigation,useNavigationGuard} from "../lib/navigation-guard";
import type {Alliance} from "../lib/types";

export function BearScheduleEditor({groupId,alliances,preferred,day,onClose,onSaved,onEvent}:{groupId:string;alliances:Alliance[];preferred?:string;day:string;onClose:()=>void;onSaved:(day:string)=>void;onEvent:(type:string)=>void}){
  const active=alliances.filter(a=>a.group_id===groupId&&a.status==="active");
  const owner=active.find(a=>a.id===preferred)?.id??active[0]?.id??"";
  const [date,setDate]=useState(day<utcDay()?utcDay():day);
  const [hours,setHours]=useState(48);
  const [slots,setSlots]=useState<(BearSlot&{id:number})[]>([{id:1,alliance_id:owner,time:"",nextDay:false}]);
  const nextId=useRef(2);
  const [rolling,setRolling]=useState(true);
  const [reviewed,setReviewed]=useState("");
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const lock=useRef(false);
  const request=useRef<{fingerprint:string;key:string}|null>(null);
  const fingerprint=JSON.stringify({date,hours,slots,rolling});
  const initial=useRef(fingerprint);
  useNavigationGuard(initial.current!==fingerprint,busy);
  let plan:ReturnType<typeof bearSchedulePlan>|null=null,validation="";
  try{plan=bearSchedulePlan(date,hours,slots,rolling);if(date<utcDay())throw Error("Choose today or a future first cycle.");}
  catch(e){plan=null;validation=e instanceof Error?e.message:"Invalid Bear schedule";}
  const patch=(id:number,change:Partial<BearSlot>)=>setSlots(old=>old.map(s=>s.id===id?{...s,...change}:s));
  async function save(e:FormEvent){
    e.preventDefault();
    if(lock.current||!plan||reviewed!==fingerprint)return;
    lock.current=true;setBusy(true);setError("");
    try{
      const payload=plan.payload;
      const keyFingerprint=JSON.stringify(payload);
      if(request.current?.fingerprint!==keyFingerprint)request.current={fingerprint:keyFingerprint,key:crypto.randomUUID()};
      await api.createBearSchedule(groupId,{...payload,request_key:request.current.key});
      onSaved(date);
    }catch(e){setError(e instanceof Error?e.message:"Unable to save Bear schedule");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section className="data-panel calendar-editor" aria-label="Schedule editor">
    <h2>Bear Trap schedule</h2>
    <p>Set the first cycle once. All traps share a cycle, and future dates are calculated automatically.</p>
    <form onSubmit={save}>
      <fieldset disabled={busy} className="calendar-editor-fields">
        <label>Event type<select value="bear:batch" onChange={e=>onEvent(e.target.value)}>
          <option value="bear:batch">Bear Trap</option><option value="bear_trap">Bear Trap (advanced single trap)</option>
          <optgroup label="Full event cycles"><option value="cycle:canyon">Canyon Clash — all phases</option><option value="cycle:svs">SvS — all phases</option></optgroup>
          {eventTypeOptions.filter(([v])=>v!=="bear_trap").map(([v,name])=><option key={v} value={v}>{name}</option>)}
          <optgroup label="Game catalog (planning only)">{extraCalendarEvents.map(event=><option key={event.id} value={"game:"+event.id}>{event.name}</option>)}</optgroup>
        </select></label>
        <label>First cycle date (UTC)<input required type="date" min={utcDay()} max="2099-12-31" value={date} onChange={e=>setDate(e.target.value)}/></label>
        <label>Repeat every (hours)<input required type="number" min={47.5} max={168} step="any" value={hours} onChange={e=>setHours(Number(e.target.value))}/></label>
      </fieldset>
      <fieldset className="bear-trap-list" disabled={busy}>
        {slots.map((slot,i)=><div className="bear-trap-slot" key={slot.id}>
          <div className="bear-trap-heading"><strong>Trap {i+1}</strong>{slots.length>1&&<button type="button" className="icon-button" aria-label={"Remove trap "+(i+1)} onClick={()=>setSlots(old=>old.filter(s=>s.id!==slot.id))}><Trash2 size={16}/></button>}</div>
          <label>Alliance<select aria-label={"Trap "+(i+1)+" alliance"} value={slot.alliance_id} onChange={e=>patch(slot.id,{alliance_id:e.target.value})}>{active.map(a=><option key={a.id} value={a.id}>{a.tag} · #{a.state_id}</option>)}</select></label>
          <label>Time (UTC)<input aria-label={"Trap "+(i+1)+" time (UTC)"} required type="time" value={slot.time} onChange={e=>patch(slot.id,{time:e.target.value})}/></label>
          <label className="calendar-checkbox"><input aria-label={"Trap "+(i+1)+" next day"} type="checkbox" checked={slot.nextDay} onChange={e=>patch(slot.id,{nextDay:e.target.checked})}/>Next UTC day</label>
        </div>)}
        <button type="button" className="button button--quiet" disabled={slots.length>=30} onClick={()=>setSlots(old=>[...old,{id:nextId.current++,alliance_id:owner,time:"",nextDay:false}])}><Plus size={16}/>Add another trap</button>
        <label className="calendar-checkbox"><input type="checkbox" checked={rolling} onChange={e=>setRolling(e.target.checked)}/>Automatically maintain schedule</label>
      </fieldset>
      <p className="muted">Each trap lasts 30 minutes. {rolling?"The first 60-day schedule is created immediately and extended automatically.":"Four cycles will be scheduled without automatic renewal."} To change an existing series, use Edit schedule on a calendar entry.</p>
      {plan?<div className="calendar-series-preview"><h3>Schedule preview</h3><p>{plan.count} cycles · {slots.length} trap{slots.length===1?"":"s"} per cycle. First dates confirmed by you; future dates estimated.</p>
        <ul>{plan.cycles.map(c=><li key={c.date}><strong>Cycle {c.date}</strong><ul>{c.traps.map(t=><li key={t.number}>Trap {t.number} · {active.find(a=>a.id===t.alliance_id)?.tag??"Alliance"} · {t.start.slice(0,10)} {t.start.slice(11,16)} UTC</li>)}</ul></li>)}</ul>
        <label className="calendar-checkbox"><input disabled={busy} type="checkbox" checked={reviewed===fingerprint} onChange={e=>setReviewed(e.target.checked?fingerprint:"")}/>I reviewed the trap times and repeat interval</label>
      </div>:<p>{validation}</p>}
      {error&&<p role="alert">{error}</p>}
      <div className="calendar-controls"><button className="button button--primary" disabled={busy||!plan||reviewed!==fingerprint} type="submit">{busy?"Saving…":"Save schedule"}</button><button type="button" className="button button--quiet" disabled={busy} onClick={()=>{if(allowNavigation())onClose();}}>Close editor</button></div>
    </form>
  </section>;
}
