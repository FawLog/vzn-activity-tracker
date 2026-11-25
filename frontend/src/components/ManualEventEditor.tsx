import { useEffect, useState } from "react";
import { api } from "../lib/api";
import { ScreenshotImport } from "./ScreenshotImport";
import type { EventRecord, ManualEvent, ManualRow, ManualSession, Player } from "../lib/types";

const definitions: Record<string, { keys: string[]; metrics: [string,string][]; registration?: boolean; battle?: boolean; attendance?: boolean }> = {
  alliance_mobilization: {keys:["main"],metrics:[["missions_completed","Completed"],["points","Points"]]},
  alliance_championship: {keys:["main"],registration:true,metrics:[]},
  foundry: {keys:["legion_1","legion_2"],registration:true,battle:true,attendance:true,metrics:[["personal_points","Personal points"]]},
  canyon: {keys:["legion_1","legion_2"],registration:true,battle:true,attendance:true,metrics:[["personal_points","Personal points"]]},
  bear_trap: {keys:["trap_1","trap_2"],attendance:true,metrics:[["damage","Damage"]]},
};
export const supportsManualEditor = (type: string) => type in definitions;
const title = (key:string) => key.replaceAll("_"," ").replace(/^./,c=>c.toUpperCase());

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
  const [paste,setPaste]=useState("");
  const [pasteKind,setPasteKind]=useState("registration");
  const [review,setReview]=useState(false);
  const [sort,setSort]=useState("nickname");
  const [confirmPublish,setConfirmPublish]=useState(false);
  const apply=(value:ManualEvent, preferred?:string)=>{
    setEditor(value);
    const session=value.sessions.find(s=>s.id===preferred) ?? value.sessions[0] ?? null;
    setSelected(session?.id ?? "");setDraft(session);setDirty(false);setReview(false);setPaste("");
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
  const add=(player:Player)=>{
    if(!draft||draft.rows.some(r=>r.fid===player.fid))return;
    change({...draft,roster_complete:false,rows:[...visibleRows,blank(player)].map(r=>({...r,eligibility:r.eligibility==="no_duty"?"no_duty":"unknown",registration:r.registration==="not_registered"?"unknown":r.registration,attendance:r.attendance==="confirmed_absent"?"unknown":r.attendance}))});
  };
  useEffect(()=>{
    let active=true;
    (async()=>{
      const items:Player[]=[];
      for(let offset=0;;offset+=100){
        const result=await api.players(groupId,"","nickname","asc",{mode:"all"},100,offset);
        items.push(...result.items);
        if(items.length>=result.total || !result.items.length)break;
      }
      if(active){setCandidates(items);setLoaded(true)}
    })().catch(e=>{if(active)setError(e instanceof Error?e.message:"Unable to load roster")});
    return ()=>{active=false};
  },[groupId]);
  const blank=(p:Player):ManualRow=>({fid:p.fid,nickname:p.nickname??p.fid,eligibility:"unknown",registration:"unknown",role:null,registered_by:null,attendance:"unknown",metrics:{}});
  const currentRoster=candidates.filter(p=>p.primary_alliance_id===record.alliance_id&&p.group_status==="active");
  const visibleRows=draft?[...draft.rows,...(editable&&!draft.roster_complete?currentRoster.filter(p=>!draft.rows.some(r=>r.fid===p.fid)).map(blank):[])]:[];
  const materialize=(rows:ManualRow[])=>{if(draft)change({...draft,rows})};
  const patchVisible=(fid:string,patch:Partial<ManualRow>)=>{
    materialize(visibleRows.map(r=>r.fid===fid?{...r,...patch}:r));
  };
  const regPatch=(row:ManualRow,checked:boolean):ManualRow=>({...row,registration:checked?"registered":"unknown",role:checked?row.role:null,registered_by:checked?row.registered_by:null,attendance:!checked&&row.attendance==="confirmed_absent"?"unknown":row.attendance});
  const bulk=(checked:boolean)=>materialize(visibleRows.map(r=>regPatch(r,checked)));
  const metricPatch=(row:ManualRow,key:string,value:string):ManualRow=>{
    const metrics={...row.metrics};
    if(value==="")delete metrics[key];else metrics[key]=Number(value);
    return {...row,metrics};
  };
  const importPaste=()=>{
    if(!draft)return;
    setError("");setMessage("");
    const kind=definition.registration?(definition.battle?pasteKind:"registration"):"metrics";
    const rows=new Map(visibleRows.map(r=>[r.fid,r]));
    const pool=new Map(candidates.map(p=>[p.fid,blank(p)]));
    for(const r of rows.values())pool.set(r.fid,r);
    const normalized=(v:string)=>v.trim().normalize("NFC").toLocaleLowerCase();
    const errors:string[]=[];const seen=new Set<string>();
    const updates:ManualRow[]=[];
    for(const [index,line] of paste.split(/\r?\n/).entries()){
      if(!line.trim())continue;
      const [name,...values]=line.split("\t").map(v=>v.trim());
      const exact=pool.get(name);
      const matches=exact?[exact]:[...pool.values()].filter(r=>normalized(r.nickname)===normalized(name));
      if(matches.length!==1){errors.push("Line "+(index+1)+": "+name+(matches.length?" is ambiguous; use ID":" not found"));continue}
      let row=matches[0];
      if(seen.has(row.fid)){errors.push("Line "+(index+1)+": duplicate player");continue}
      seen.add(row.fid);
      if(kind==="registration"){
        if(values.length){errors.push("Line "+(index+1)+": expected one name or ID");continue}
        row=regPatch(row,true);
      }else if(kind==="main"||kind==="substitute"){
        if(values.length){errors.push("Line "+(index+1)+": expected one name or ID");continue}
        row={...regPatch(row,true),role:kind};
      }else{
        const columns=definition.metrics;
        if(values.length!==columns.length||values.some(v=>!/^\d+$/.test(v)||!Number.isSafeInteger(Number(v)))){errors.push("Line "+(index+1)+": expected "+columns.map(c=>c[1]).join(", "));continue}
        for(let i=0;i<columns.length;i++)row=metricPatch(row,columns[i][0],values[i]);
        if(definition.attendance&&values.some(v=>Number(v)>0))row={...row,attendance:"confirmed_present"};
      }
      updates.push(row);
    }
    if(errors.length){setError(errors.join("; "));return}
    if(!updates.length){setError("Paste at least one player.");return}
    for(const row of updates)rows.set(row.fid,row);
    change({...draft,roster_complete:updates.some(r=>!visibleRows.some(v=>v.fid===r.fid))?false:draft.roster_complete,rows:[...rows.values()].map(r=>updates.some(u=>!visibleRows.some(v=>v.fid===u.fid))?{...r,eligibility:r.eligibility==="no_duty"?"no_duty":"unknown",registration:r.registration==="not_registered"?"unknown":r.registration,attendance:r.attendance==="confirmed_absent"?"unknown":r.attendance}:r)});setPaste("");setMessage("Imported "+updates.length+" players into draft. Review before saving.");
  };
  const confirmRoster=(checked:boolean)=>{
    if(!draft)return;
    materialize(visibleRows.map(r=>({...r,eligibility:r.eligibility==="no_duty"?"no_duty":checked?"confirmed":"unknown",registration:!checked&&r.registration==="not_registered"?"unknown":r.registration,attendance:!checked&&r.attendance==="confirmed_absent"?"unknown":r.attendance})));
    setDraft(old=>old?{...old,roster_complete:checked}:old);
  };
  const complete=(field:"registration_complete"|"attendance_complete"|"results_complete",checked:boolean)=>{
    if(!draft)return;
    change({...draft,[field]:checked,rows:visibleRows.map(r=>({...r,registration:field==="registration_complete"&&!checked&&r.registration==="not_registered"?"unknown":r.registration,attendance:field==="attendance_complete"&&!checked&&r.attendance==="confirmed_absent"?"unknown":r.attendance}))});
  };
  const save=async()=>{
    if(!draft)return;
    const rows=visibleRows.map(r=>({...r,registration:definition.registration&&draft.roster_complete&&draft.registration_complete&&r.eligibility==="confirmed"&&r.registration==="unknown"?"not_registered" as const:r.registration,attendance:r.attendance}));
    const v=await api.saveEventSession(groupId,record.id,draft.id,{revision:draft.revision,roster_complete:!!draft.roster_complete,registration_complete:!!draft.registration_complete,attendance_complete:!!draft.attendance_complete,results_complete:!!draft.results_complete,rows});
    apply(v,draft.id);setMessage("Draft saved.");
  };
  const available=definition.keys.filter(k=>!editor?.sessions.some(s=>s.session_key===k));
  const selectField=(row:ManualRow,field:keyof typeof choices)=><select aria-label={row.nickname+" "+title(field)} value={row[field]??""} disabled={!editable||busy} onChange={e=>{
    const value=e.target.value;
    const patch={ [field]:value||null } as Partial<ManualRow>;
    if(field==="attendance"&&value==="confirmed_absent"&&(!draft?.roster_complete||!draft.attendance_complete||row.eligibility!=="confirmed")){setError("Confirm historical roster and attendance evidence in Review completeness before marking an absence.");return;}
    if(field==="attendance"&&value==="confirmed_absent"&&Object.values(row.metrics).some(v=>v>0)){setError("A positive score conflicts with absence.");return;}
    if(field==="registration"&&value!=="registered"){patch.role=null;patch.registered_by=null}
    if(field==="role"&&value)patch.registration="registered";
    patchVisible(row.fid,patch);
  }}>{choices[field].map(v=><option key={v} value={v}>{v?title(v):"—"}</option>)}</select>;
  return <section className="data-panel data-panel--page manual-editor">
    <div className="section-header"><div><h2>Manual results</h2><p>Session records, reviewed by an officer. Missing data remains unknown.</p></div></div>
    {error&&<div className="notice notice--error" role="alert">{error}</div>}{message&&<div className="notice notice--success" role="status">{message}</div>}
    {!editor&&!error&&<p className="manual-help">Loading editor…</p>}
    {editor&&<><div className="manual-controls">
      {editor.sessions.map(s=><button key={s.id} className="button button--quiet" disabled={busy||dirty} aria-pressed={selected===s.id} onClick={()=>{setSelected(s.id);setDraft(s);setConfirmPublish(false);setReview(false);setPaste("")}}>{title(s.session_key)}</button>)}
      {editable&&available.length>0&&<><label>Session<select value={available.includes(sessionKey)?sessionKey:available[0]} onChange={e=>setSessionKey(e.target.value)}>{available.map(k=><option key={k} value={k}>{title(k)}</option>)}</select></label><label>Start UTC<input type="datetime-local" value={time} onChange={e=>setTime(e.target.value)}/></label><button className="button button--secondary" disabled={busy||dirty||!time} onClick={()=>void run(async()=>{const k=available.includes(sessionKey)?sessionKey:available[0];const v=await api.createEventSession(groupId,record.id,k,time+":00Z");apply(v,v.sessions.find(s=>s.session_key===k)?.id)})}>Add session</button></>}
    </div>
    {draft&&<><p className="manual-help">{draft.started_at.slice(0,16).replace("T"," ")} UTC · {visibleRows.length} players{!loaded&&editable?" · Loading roster…":""}</p>
    {editable&&<><div className="manual-controls">
      <label>Find player<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name or ID"/></label>
      <label>Sort<select value={sort} onChange={e=>setSort(e.target.value)}><option value="nickname">Name</option>{definition.metrics.map(([key,label])=><option key={key} value={key}>{label} (highest first)</option>)}</select></label>
      {definition.registration&&<><button className="button button--quiet" disabled={busy||!loaded} onClick={()=>bulk(true)}>Register all</button><button className="button button--quiet" disabled={busy||!loaded} onClick={()=>bulk(false)}>Clear registrations</button><span>{visibleRows.filter(r=>r.registration==="registered").length} registered</span></>}
    </div>
    <ScreenshotImport key={groupId+":"+record.id+":"+draft.id} groupId={groupId} eventId={record.id} sessionId={draft.id} disabled={busy} onBusy={setBusy} />
    <div className="manual-import">
      <h3>Paste a list</h3>
      {definition.battle&&<label>List type<select value={pasteKind} onChange={e=>setPasteKind(e.target.value)}><option value="registration">Registered players</option><option value="main">Main players</option><option value="substitute">Substitutes</option><option value="metrics">Personal points</option></select></label>}
      <p className="manual-help">{definition.registration&&(!definition.battle||pasteKind!=="metrics")?"One player name or ID per line.":"Paste spreadsheet columns separated by tabs: player name or ID, "+definition.metrics.map(c=>c[1]).join(", ")+". "} Exact matches only; ambiguous names require ID. No changes are applied if any line fails.</p>
      <textarea aria-label="Paste player list" rows={4} value={paste} onChange={e=>setPaste(e.target.value)} placeholder="Paste here…"/>
      <button className="button button--secondary" disabled={busy||!loaded||!paste.trim()} onClick={importPaste}>Import list</button>
    </div>
    {query.trim()&&<div className="manual-controls">{candidates.filter(p=>!visibleRows.some(r=>r.fid===p.fid)&&((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.toLowerCase())).slice(0,15).map(p=><button className="button button--quiet" key={p.fid} disabled={busy} onClick={()=>add(p)}>Add {p.nickname??p.fid}</button>)}</div>}
    </>}
    <div className="table-wrap"><table><thead><tr><th>Player / ID</th>{definition.registration&&<th>Registered</th>}{definition.battle&&<th>Role</th>}{definition.attendance&&(definition.battle||review||!editable)&&<th>Attendance</th>}{definition.metrics.map(([k,l])=><th key={k}>{l}</th>)}{editable&&review&&<th>Roster exception</th>}</tr></thead><tbody>
    {visibleRows.filter(r=>!query.trim()|| (r.nickname+" "+r.fid).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==="nickname"?a.nickname.localeCompare(b.nickname):(b.metrics[sort]??-1)-(a.metrics[sort]??-1)).map(row=><tr key={row.fid}><td>{row.nickname}<small className="table-subline mono">{row.fid}</small></td>
    {definition.registration&&<td><input type="checkbox" aria-label={row.nickname+" Registered"} checked={row.registration==="registered"} disabled={!editable||busy} onChange={e=>patchVisible(row.fid,regPatch(row,e.target.checked))}/>{row.registration==="unknown"&&!editable?" Unknown":row.registration==="excused"?" Excused":""}</td>}
    {definition.battle&&<td>{selectField(row,"role")}</td>}
    {definition.attendance&&(definition.battle||review||!editable)&&<td>{selectField(row,"attendance")}</td>}
    {definition.metrics.map(([key,label])=><td key={key}><input type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} aria-label={row.nickname+" "+label} disabled={!editable||busy} value={row.metrics[key]??""} onChange={e=>{const next=metricPatch(row,key,e.target.value);if(definition.attendance&&Number(e.target.value)>0)next.attendance="confirmed_present";patchVisible(row.fid,next)}}/></td>)}
    {editable&&review&&<td><label><input type="checkbox" checked={row.eligibility==="no_duty"} onChange={e=>patchVisible(row.fid,{eligibility:e.target.checked?"no_duty":draft.roster_complete?"confirmed":"unknown",registration:row.registration==="not_registered"?"unknown":row.registration,attendance:row.attendance==="confirmed_absent"?"unknown":row.attendance})}/>Not eligible</label></td>}
    </tr>)}
    </tbody></table></div>
    {editable&&<><div className="manual-controls"><button className="button button--primary" disabled={busy||!loaded||(!dirty&&draft.rows.length===0&&visibleRows.length===0)} onClick={()=>void run(save)}>Save draft</button><button className="button button--secondary" disabled={busy||!loaded} onClick={()=>setReview(v=>!v)}>Review completeness</button>{dirty&&<span>Unsaved changes</span>}</div>
    {review&&<div className="manual-review"><h3>Review before publishing</h3><p>Leave unchecked if the information is partial. Missing entries remain unknown.</p>
    <label><input type="checkbox" checked={!!draft.roster_complete} onChange={e=>confirmRoster(e.target.checked)}/>This is the full alliance roster at the time of the event (mark exceptions in the table).</label>
    {definition.registration&&<label><input type="checkbox" checked={!!draft.registration_complete} onChange={e=>complete("registration_complete",e.target.checked)}/>I entered the complete registration list.</label>}
    {definition.attendance&&<label><input type="checkbox" checked={!!draft.attendance_complete} onChange={e=>complete("attendance_complete",e.target.checked)}/>I verified who actually attended, not just who scored points. Mark confirmed absences explicitly in the table.</label>}
    {!definition.registration&&!definition.attendance&&<label><input type="checkbox" checked={!!draft.results_complete} onChange={e=>complete("results_complete",e.target.checked)}/>I entered the full results list.</label>}
    <p>Only confirmed eligible players can be marked absent or not registered. Blank and zero scores never automatically become absences.</p>
    <button className="button button--primary" disabled={busy} onClick={()=>void run(save)}>Save reviewed draft</button></div>}</>}
    </>}
    {editable&&editor.sessions.length>0&&<div className="manual-controls"><label><input type="checkbox" checked={confirmPublish} disabled={dirty||busy} onChange={e=>setConfirmPublish(e.target.checked)}/>I reviewed all recorded sessions (unknown remains unknown)</label><button className="button button--secondary" disabled={busy||dirty||!confirmPublish} onClick={()=>void run(async()=>{apply(await api.publishEvent(groupId,record.id),selected);setConfirmPublish(false);onPublished();setMessage("Event published.")})}>Publish event</button></div>}
    </>}
  </section>;
}
