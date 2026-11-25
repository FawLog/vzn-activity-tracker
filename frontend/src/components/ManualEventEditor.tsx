import { useEffect, useState } from "react";
import { api } from "../lib/api";
import type { EventRecord, ManualEvent, ManualRow, ManualSession, Player } from "../lib/types";

const definitions: Record<string, { keys: string[]; metrics: [string,string][]; registration?: boolean; battle?: boolean; attendance?: boolean }> = {
  alliance_mobilization: {keys:["main"],metrics:[["rank","Rank"],["missions_completed","Completed"],["missions_accepted","Accepted"],["points","Points"]]},
  alliance_championship: {keys:["main"],registration:true,metrics:[["registration_value","Registration value"]]},
  foundry: {keys:["legion_1","legion_2"],registration:true,battle:true,attendance:true,metrics:[["rank","Rank"],["personal_points","Personal points"]]},
  canyon: {keys:["legion_1","legion_2"],registration:true,battle:true,attendance:true,metrics:[["rank","Rank"],["personal_points","Personal points"]]},
  bear_trap: {keys:["trap_1","trap_2"],attendance:true,metrics:[["rank","Rank"],["damage","Damage"]]},
};
export const supportsManualEditor = (type: string) => type in definitions;
const title = (key:string) => key.replaceAll("_"," ").replace(/^./,c=>c.toUpperCase());
const flags = ["roster_complete","registration_complete","attendance_complete","results_complete"] as const;
const choices = {
  eligibility: ["unknown","confirmed","no_duty"],
  registration: ["unknown","registered","not_registered","excused"],
  role: ["","main","substitute"],
  registered_by: ["","unknown","player","officer"],
  attendance: ["unknown","confirmed_present","confirmed_absent","excused","no_duty"],
} as const;

export function ManualEventEditor({groupId,record,onPublished}:{groupId:string;record:EventRecord;onPublished:()=>void}) {
  const definition=definitions[record.event_type];
  const [editor,setEditor]=useState<ManualEvent|null>(null);
  const [selected,setSelected]=useState("");
  const [draft,setDraft]=useState<ManualSession|null>(null);
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [time,setTime]=useState(record.occurred_on+"T00:00");
  const [sessionKey,setSessionKey]=useState(definition.keys[0]);
  const [candidates,setCandidates]=useState<Player[]>([]);
  const [query,setQuery]=useState("");
  const [loaded,setLoaded]=useState(false);
  const [confirmPublish,setConfirmPublish]=useState(false);
  const apply=(value:ManualEvent, preferred?:string)=>{
    setEditor(value);
    const session=value.sessions.find(s=>s.id===preferred) ?? value.sessions[0] ?? null;
    setSelected(session?.id ?? "");setDraft(session);setDirty(false);
  };
  useEffect(()=>{
    let active=true;
    api.eventEditor(groupId,record.id).then(v=>{if(active)apply(v)}).catch(e=>{if(active)setError(String(e.message))});
    return ()=>{active=false};
  },[groupId,record.id]);
  useEffect(()=>{
    if(!dirty)return;
    const handler=(event:BeforeUnloadEvent)=>{event.preventDefault();event.returnValue=""};
    window.addEventListener("beforeunload",handler);
    return ()=>window.removeEventListener("beforeunload",handler);
  },[dirty]);
  const run=async(action:()=>Promise<void>)=>{
    setBusy(true);setError("");setMessage("");
    try{await action()}catch(e){setError(e instanceof Error?e.message:"Request failed")}finally{setBusy(false)}
  };
  const editable=editor?.status==="draft";
  const change=(next:ManualSession)=>{setDraft(next);setDirty(true);setConfirmPublish(false)};
  const editRow=(fid:string,patch:Partial<ManualRow>)=>{
    if(!draft)return;
    change({...draft,rows:draft.rows.map(r=>r.fid===fid?{...r,...patch}:r)});
  };
  const add=(player:Player)=>{
    if(!draft||draft.rows.some(r=>r.fid===player.fid))return;
    change({...draft,rows:[...draft.rows,{fid:player.fid,nickname:player.nickname??player.fid,eligibility:"unknown",registration:"unknown",role:null,registered_by:null,attendance:"unknown",metrics:{}}]});
  };
  const load=()=>run(async()=>{
    const items:Player[]=[];
    for(let offset=0;;offset+=100){
      const result=await api.players(groupId,"","nickname","asc",{mode:"all"},100,offset);
      items.push(...result.items);
      if(items.length>=result.total || !result.items.length)break;
    }
    setCandidates(items);setLoaded(true);
  });
  const available=definition.keys.filter(k=>!editor?.sessions.some(s=>s.session_key===k));
  const selectField=(row:ManualRow,field:keyof typeof choices)=><select aria-label={row.nickname+" "+title(field)} value={row[field]??""} disabled={!editable||busy} onChange={e=>{
    const value=e.target.value;
    const patch={ [field]:value||null } as Partial<ManualRow>;
    if(field==="registration"&&value!=="registered"){patch.role=null;patch.registered_by=null}
    editRow(row.fid,patch);
  }}>{choices[field].map(v=><option key={v} value={v}>{v?title(v):"—"}</option>)}</select>;
  return <section className="data-panel data-panel--page manual-editor">
    <div className="section-header"><div><h2>Manual results</h2><p>Session records, reviewed by an officer. Missing data remains unknown.</p></div></div>
    {error&&<div className="notice notice--error" role="alert">{error}</div>}{message&&<div className="notice notice--success" role="status">{message}</div>}
    {!editor&&!error&&<p className="manual-help">Loading editor…</p>}
    {editor&&<><div className="manual-controls">
      {editor.sessions.map(s=><button key={s.id} className="button button--quiet" disabled={busy||dirty} aria-pressed={selected===s.id} onClick={()=>{setSelected(s.id);setDraft(s);setConfirmPublish(false)}}>{title(s.session_key)}</button>)}
      {editable&&available.length>0&&<><label>Session<select value={available.includes(sessionKey)?sessionKey:available[0]} onChange={e=>setSessionKey(e.target.value)}>{available.map(k=><option key={k} value={k}>{title(k)}</option>)}</select></label><label>Start UTC<input type="datetime-local" value={time} onChange={e=>setTime(e.target.value)}/></label><button className="button button--secondary" disabled={busy||dirty||!time} onClick={()=>void run(async()=>{const k=available.includes(sessionKey)?sessionKey:available[0];const v=await api.createEventSession(groupId,record.id,k,time+":00Z");apply(v,v.sessions.find(s=>s.session_key===k)?.id)})}>Add session</button></>}
    </div>
    {draft&&<><p className="manual-help">{draft.started_at.slice(0,16).replace("T"," ")} UTC · {draft.rows.length} roster records. Confirm historical eligibility manually; current membership is not proof of past membership.</p>
    {editable&&<div className="manual-controls"><button className="button button--quiet" disabled={busy} onClick={()=>void load()}>Load group players</button>{loaded&&<><label>Find player<input value={query} onChange={e=>setQuery(e.target.value)}/></label><button className="button button--quiet" disabled={busy} onClick={()=>{const ids=new Set(draft.rows.map(r=>r.fid));change({...draft,rows:[...draft.rows,...candidates.filter(p=>p.primary_alliance_id===record.alliance_id&&p.group_status!=="archived"&&!ids.has(p.fid)).map(p=>({fid:p.fid,nickname:p.nickname??p.fid,eligibility:"unknown" as const,registration:"unknown" as const,role:null,registered_by:null,attendance:"unknown" as const,metrics:{}}))]})}}>Add current alliance roster as unknown</button></>}</div>}
    {editable&&loaded&&<div className="manual-controls">{candidates.filter(p=>!draft.rows.some(r=>r.fid===p.fid)&&((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.toLowerCase())).slice(0,30).map(p=><button className="button button--quiet" key={p.fid} disabled={busy} onClick={()=>add(p)}>Add {p.nickname??p.fid}</button>)}</div>}
    <div className="manual-controls">{flags.filter(f=>f==="roster_complete"||f==="results_complete"||f==="registration_complete"&&definition.registration||f==="attendance_complete"&&definition.attendance).map(f=><label key={f}><input type="checkbox" checked={!!draft[f]} disabled={!editable||busy} onChange={e=>change({...draft,[f]:e.target.checked})}/>{title(f)}</label>)}</div>
    <div className="table-wrap"><table><thead><tr><th>Player / ID</th><th>Eligibility</th>{definition.registration&&<th>Registration</th>}{definition.battle&&<><th>Role</th><th>Registered by</th></>}{definition.attendance&&<th>Attendance</th>}{definition.metrics.map(([k,l])=><th key={k}>{l}</th>)}{editable&&<th>Remove</th>}</tr></thead><tbody>
    {draft.rows.map(row=><tr key={row.fid}><td>{row.nickname}<small className="table-subline mono">{row.fid}</small></td><td>{selectField(row,"eligibility")}</td>{definition.registration&&<td>{selectField(row,"registration")}</td>}{definition.battle&&<><td>{selectField(row,"role")}</td><td>{selectField(row,"registered_by")}</td></>}{definition.attendance&&<td>{selectField(row,"attendance")}</td>}{definition.metrics.map(([key,label])=><td key={key}><input type="number" min={key==="rank"?1:0} max={Number.MAX_SAFE_INTEGER} step={1} aria-label={row.nickname+" "+label} disabled={!editable||busy} value={row.metrics[key]??""} onChange={e=>{const metrics={...row.metrics};if(e.target.value==="")delete metrics[key];else metrics[key]=Number(e.target.value);editRow(row.fid,{metrics})}}/></td>)}{editable&&<td><button className="button button--quiet" disabled={busy} aria-label={"Remove "+row.nickname} onClick={()=>change({...draft,rows:draft.rows.filter(r=>r.fid!==row.fid)})}>Remove</button></td>}</tr>)}
    </tbody></table></div>
    {editable&&<div className="manual-controls"><button className="button button--primary" disabled={busy||!dirty} onClick={()=>void run(async()=>{const {id,session_key,started_at,...payload}=draft;void session_key;void started_at;const v=await api.saveEventSession(groupId,record.id,id,{...payload,roster_complete:!!payload.roster_complete,registration_complete:!!payload.registration_complete,attendance_complete:!!payload.attendance_complete,results_complete:!!payload.results_complete});apply(v,id);setMessage("Draft saved.")})}>Save draft</button>{dirty&&<span>Unsaved changes</span>}</div>}
    </>}
    {editable&&editor.sessions.length>0&&<div className="manual-controls"><label><input type="checkbox" checked={confirmPublish} disabled={dirty||busy} onChange={e=>setConfirmPublish(e.target.checked)}/>I reviewed all recorded sessions (unknown remains unknown)</label><button className="button button--secondary" disabled={busy||dirty||!confirmPublish} onClick={()=>void run(async()=>{apply(await api.publishEvent(groupId,record.id),selected);setConfirmPublish(false);onPublished();setMessage("Event published.")})}>Publish event</button></div>}
    </>}
  </section>;
}
