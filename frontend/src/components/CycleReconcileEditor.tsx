import {useEffect,useRef,useState} from "react";
import {api} from "../lib/api";
import {addDays} from "../lib/calendar";
import {useNavigationGuard} from "../lib/navigation-guard";
import type {CycleReconcilePlan,CycleSeries,CycleReconcilePayload} from "../lib/calendar-cycles";

export function CycleReconcileEditor({groupId,cycleId,series,onChanged}:{groupId:string;cycleId:string;series:CycleSeries|null;onChanged:(day?:string)=>void}){
  const [open,setOpen]=useState(false);
  const [following,setFollowing]=useState(false);
  const [days,setDays]=useState(0);
  const [plan,setPlan]=useState<CycleReconcilePlan|null>(null);
  const [error,setError]=useState("");
  const [busy,setBusy]=useState(false);
  const [review,setReview]=useState(false);
  const lock=useRef(false);
  useNavigationGuard(open&&(days!==0||following||review),busy);
  useEffect(()=>{
    if(!open)return;
    const controller=new AbortController();
    setPlan(null);setReview(false);setError("");
    api.cycleReconcilePreview(groupId,cycleId,following,controller.signal).then(p=>{if(!controller.signal.aborted)setPlan(p);}).catch(e=>{if(!controller.signal.aborted)setError(e instanceof Error?e.message:"Unable to review cycle");});
    return ()=>controller.abort();
  },[groupId,cycleId,following,open]);
  const validDays=Number.isInteger(days)&&days!==0&&Math.abs(days)<=366;
  async function apply(action:CycleReconcilePayload["action"]){
    if(lock.current||!plan||!review||action==="shift"&&(!validDays||!plan.items.length)||action==="confirm"&&!plan.can_confirm)return;
    lock.current=true;setBusy(true);setError("");
    try{
      const rows=action==="confirm"?plan.confirm_items:action==="shift"?plan.items:[];
      const result=await api.reconcileCycle(groupId,cycleId,{action,following:action==="shift"&&following,shift_days:action==="shift"?days:0,revisions:Object.fromEntries(rows.map(r=>[r.id,r.revision])),series_revision:plan.series_revision});
      onChanged(result.items[0]?.starts_at.slice(0,10));
    }catch(e){setError(e instanceof Error?e.message:"Unable to update cycle");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section className="calendar-editor-fields" aria-label="Cycle reconciliation">
    <button className="button button--quiet" type="button" disabled={busy} onClick={()=>{setOpen(v=>!v);setDays(0);setFollowing(false);setReview(false);setPlan(null);}}>{open?"Close cycle review":"Review cycle dates"}</button>
    {open&&<><p>Confirm dates against the game calendar, or shift only untouched future forecasts. Unknown battle times remain unset. Confirmed, edited, cancelled, started and linked cycles are protected from shifts.</p>
      {series&&<label className="calendar-checkbox"><input type="checkbox" disabled={busy} checked={following} onChange={e=>{setFollowing(e.target.checked);setPlan(null);setReview(false);}}/>This and following cycles</label>}
      <label>Move by days (UTC)<input type="number" min={-366} max={366} disabled={busy} value={days} onChange={e=>{setDays(Number(e.target.value));setReview(false);}}/></label>
      {plan&&<><p>{new Set(plan.items.map(r=>r.cycle_id)).size} movable cycles · {plan.protected_cycles} protected cycles.</p>
      {validDays&&<ul>{plan.items.map(r=><li key={r.id}>{r.phase}: {r.starts_at} → {addDays(r.starts_at.slice(0,10),days)+r.starts_at.slice(10)}</li>)}</ul>}
      {!following&&days===0&&plan.can_confirm&&<ul>{plan.confirm_items.map(r=><li key={r.id}>{r.phase}: {r.starts_at}{r.ends_at?" – "+r.ends_at:""}</li>)}</ul>}
      <label className="calendar-checkbox"><input type="checkbox" disabled={busy} checked={review} onChange={e=>setReview(e.target.checked)}/>I reviewed the dates and selected operation</label>
      <div className="calendar-controls">
        <button type="button" className="button button--quiet" disabled={busy||!review||!plan.can_confirm||following||days!==0} onClick={()=>void apply("confirm")}>Confirm cycle dates</button>
        <button type="button" className="button button--primary" disabled={busy||!review||!validDays||!plan.items.length} onClick={()=>void apply("shift")}>Move forecast cycles</button>
        {plan.series_status&&["active","conflict"].includes(plan.series_status)&&<button type="button" className="button button--quiet" disabled={busy||!review||following||days!==0} onClick={()=>void apply("stop")}>Stop automatic renewal</button>}
      </div></>}
      {!plan&&!error&&<p>Loading review…</p>}{error&&<p role="alert">{error}</p>}
    </>}
  </section>;
}
