import { useEffect, useState } from "react";
import { Plus, Trash2, X } from "lucide-react";
import { api } from "../lib/api";
import type { ReviewRow } from "../lib/ocrReview";
import type { FoundryImportInfo } from "../lib/ocrParser";
import { AttendanceFinalReview } from "./AttendanceFinalReview";
import { ScreenshotImport } from "./ScreenshotImport";
import { championshipSummary, championshipRows, invalidateChampionship } from "../lib/championship";
import type { Alliance, EventRecord, ManualEvent, ManualRow, ManualSession, Player } from "../lib/types";

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
  const single=definition.keys.length===1;
  const bear=record.event_type==="bear_trap";
  const sessionNoun=bear?"trap":"legion";
  const championship=record.event_type==="alliance_championship";
  const foundry=record.event_type==="foundry";
  const [foundryStage,setFoundryStage]=useState<"registration"|"results">("registration");
  const [editor,setEditor]=useState<ManualEvent|null>(null);
  const [selected,setSelected]=useState("");
  const [draft,setDraft]=useState<ManualSession|null>(null);
  const [dirty,setDirty]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  const [error,setError]=useState("");
  const [time,setTime]=useState(record.occurred_on+"T00:00");
  const [sessionKey,setSessionKey]=useState(definition.keys[0]);
  const [addingSession,setAddingSession]=useState(false);
  const [hosts,setHosts]=useState<Alliance[]>([]);
  const [host,setHost]=useState(record.alliance_id);
  useEffect(()=>{if(record.event_type==="bear_trap")api.alliances(groupId).then(v=>setHosts(v.items.filter(a=>a.status==="active"))).catch(e=>setError(String(e.message)))},[groupId,record.event_type]);
  const [candidates,setCandidates]=useState<Player[]>([]);
  const [query,setQuery]=useState("");
  const [loaded,setLoaded]=useState(false);
  const [paste,setPaste]=useState("");
  const [pasteKind,setPasteKind]=useState("registration");
  const [review,setReview]=useState(false);
  const [expectedRegistered,setExpectedRegistered]=useState("");
  const [expectedRoster,setExpectedRoster]=useState("");
  const [rosterAttested,setRosterAttested]=useState(false);
  const [sort,setSort]=useState("nickname");
  const [confirmPublish,setConfirmPublish]=useState(false);
  const [cycleComplete,setCycleComplete]=useState(false);
  const apply=(value:ManualEvent, preferred?:string)=>{
    setEditor(value);setCycleComplete(false);setAddingSession(false);
    const session=value.sessions.find(s=>s.id===preferred) ?? value.sessions[0] ?? null;
    setSelected(session?.id ?? "");setDraft(session);setDirty(false);setReview(false);setPaste("");setRosterAttested(false);setExpectedRegistered(session?.registration_complete?String(session.rows.filter(r=>r.registration==="registered").length):"");setExpectedRoster(session?.roster_complete?String(session.rows.length):"");
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
  const change=(next:ManualSession)=>{setDraft(championship?invalidateChampionship(next):next);setDirty(true);setConfirmPublish(false);setRosterAttested(false)};
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
  const currentRoster=candidates.filter(p=>p.primary_alliance_id===(draft?.host_alliance_id??record.alliance_id)&&p.group_status==="active");
  const visibleRows=draft?[...draft.rows,...(editable&&!draft.roster_complete?currentRoster.filter(p=>!draft.rows.some(r=>r.fid===p.fid)).map(blank):[])]:[];
  const champSummary=championshipSummary(visibleRows,!!draft?.roster_complete&&!!draft?.registration_complete);
  const materialize=(rows:ManualRow[])=>{if(draft)change({...draft,rows})};
  const patchVisible=(fid:string,patch:Partial<ManualRow>)=>{
    if(foundry&&draft){const reg="registration" in patch||"role" in patch;const score="metrics" in patch;change({...draft,rows:visibleRows.map(r=>r.fid===fid?{...r,...patch}:r),registration_complete:reg?false:draft.registration_complete,results_complete:reg||score?false:draft.results_complete,attendance_complete:reg||score?false:draft.attendance_complete});return}
    materialize(visibleRows.map(r=>r.fid===fid?{...r,...patch}:r));
  };
  const regPatch=(row:ManualRow,checked:boolean):ManualRow=>({...row,registration:checked?"registered":"unknown",role:checked?row.role:null,registered_by:checked?row.registered_by:null,attendance:!checked&&row.attendance==="confirmed_absent"?"unknown":row.attendance});
  const bulk=(checked:boolean)=>{if(foundry&&draft){change({...draft,rows:visibleRows.map(r=>regPatch(r,checked)),registration_complete:false,results_complete:false,attendance_complete:false});return}materialize(visibleRows.map(r=>regPatch(r,checked)))};
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
    change({...draft,...(foundry?{registration_complete:false,results_complete:false,attendance_complete:false}:{}),roster_complete:updates.some(r=>!visibleRows.some(v=>v.fid===r.fid))?false:draft.roster_complete,rows:[...rows.values()].map(r=>updates.some(u=>!visibleRows.some(v=>v.fid===u.fid))?{...r,eligibility:r.eligibility==="no_duty"?"no_duty":"unknown",registration:r.registration==="not_registered"?"unknown":r.registration,attendance:r.attendance==="confirmed_absent"?"unknown":r.attendance}:r)});setPaste("");if(championship)setReview(true);setMessage("Imported "+updates.length+" players into draft. Review before saving.");
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
    const rows=championship?championshipRows(visibleRows,!!draft.roster_complete&&!!draft.registration_complete):visibleRows.map(r=>({...r,registration:definition.registration&&draft.roster_complete&&draft.registration_complete&&r.eligibility==="confirmed"&&r.registration==="unknown"?"not_registered" as const:r.registration,attendance:r.attendance}));
    const v=await api.saveEventSession(groupId,record.id,draft.id,{revision:draft.revision,roster_complete:!!draft.roster_complete,registration_complete:!!draft.registration_complete,attendance_complete:!!draft.attendance_complete,results_complete:!!draft.results_complete,rows,...(foundry?{foundry_details:draft.foundry_details??{}}:{})});
    apply(v,draft.id);setMessage("Draft saved.");
  };
  const importOcr=async(imported:ReviewRow[],info?:FoundryImportInfo,stage?:"registration"|"results")=>{
    if(!draft||!editable||!loaded||busy)throw new Error("Wait for the roster and draft to finish loading.");
    if(dirty)throw new Error("Save or discard manual changes before importing OCR results.");
    const rows=new Map(visibleRows.map(r=>[r.fid,r]));
    const pool=new Map(candidates.map(p=>[p.fid,blank(p)]));
    const seen=new Set<string>();
    let added=false,overwrites=0;
    for(const entry of imported){
      if(!entry.fid||seen.has(entry.fid)||!entry.include||!["exact","manual"].includes(entry.match))throw new Error("Review player matches before importing.");
      seen.add(entry.fid);
      const existing=rows.get(entry.fid);
      let row=existing??pool.get(entry.fid);
      if(!row)throw new Error("Player no longer belongs to this group.");
      if(!existing)added=true;
      if(record.event_type==="alliance_championship"){
        if(row.registration==="not_registered"||row.registration==="excused")overwrites++;
        row=regPatch(row,true);
      }else if(record.event_type==="bear_trap"){
        const damage=entry.damage;
        if(damage===undefined||!Number.isSafeInteger(damage)||damage<=0)throw new Error("Invalid damage.");
        if((row.metrics.damage!==undefined&&row.metrics.damage!==damage)||row.attendance==="confirmed_absent"||row.attendance==="excused")overwrites++;
        row={...row,attendance:"confirmed_present",metrics:{...row.metrics,damage}};
      }else if(foundry&&stage==="registration"){
        if(!entry.role)throw new Error("Confirm main/substitute role.");
        if(row.registration==="not_registered"||row.registration==="excused"||(row.role&&row.role!==entry.role))overwrites++;
        row={...regPatch(row,true),role:entry.role,registered_by:row.registered_by??"unknown"};
      }else if(foundry&&stage==="results"){
        const points=entry.points;
        if(points===undefined||!Number.isSafeInteger(points)||points<0)throw new Error("Invalid personal points.");
        if((row.metrics.personal_points!==undefined&&row.metrics.personal_points!==points)||row.attendance==="excused"||row.attendance==="no_duty")overwrites++;
        row={...row,attendance:points>0?"confirmed_present":"unknown",metrics:{...row.metrics,personal_points:points,...(entry.rank!==undefined?{rank:entry.rank}:{})}};
      }else if(record.event_type==="alliance_mobilization"){
        const {completed,total,points}=entry;
        if(completed===undefined||total===undefined||points===undefined||![completed,total,points].every(n=>Number.isSafeInteger(n)&&n>=0)||completed>total)throw new Error("Invalid missions or points.");
        if((row.metrics.points!==undefined&&row.metrics.points!==points)||(row.metrics.missions_completed!==undefined&&row.metrics.missions_completed!==completed))overwrites++;
        row={...row,metrics:{...row.metrics,missions_completed:completed,points}};
      }else throw new Error("Automatic import is not supported for this event.");
      rows.set(entry.fid,row);
    }
    if(!seen.size)throw new Error("No reviewed players to import.");
    if(foundry&&info&&Object.entries(info).some(([k,v])=>v!==undefined&&draft.foundry_details?.[k as keyof FoundryImportInfo]!=null&&draft.foundry_details?.[k as keyof FoundryImportInfo]!==v))overwrites++;
    if(overwrites&&!window.confirm("Replace existing results or registration for "+overwrites+" players?"))throw new Error("Import cancelled; existing results unchanged.");
    const nextRows=[...rows.values()].map(r=>added||championship?{...r,eligibility:r.eligibility==="no_duty"?"no_duty" as const:"unknown" as const,registration:r.registration==="not_registered"?"unknown" as const:r.registration,attendance:r.attendance==="confirmed_absent"?"unknown" as const:r.attendance}:r);
    setBusy(true);setError("");setMessage("");
    try{
      const result=await api.saveEventSession(groupId,record.id,draft.id,{revision:draft.revision,roster_complete:added||championship?false:draft.roster_complete,registration_complete:championship||foundry&&stage==="registration"?false:draft.registration_complete,attendance_complete:foundry?false:draft.attendance_complete,results_complete:foundry?false:draft.results_complete,rows:nextRows,...(foundry?{foundry_details:{...draft.foundry_details,...Object.fromEntries(Object.entries(info??{}).filter(([,v])=>v!==undefined))}}:{})});
      apply(result,draft.id);setConfirmPublish(false);if(championship)setReview(true);setMessage("Imported "+seen.size+" players and saved draft. Review before publishing.");
    }finally{setBusy(false)}
  };
  const available=(record.event_type==="bear_trap"?Array.from({length:30},(_,i)=>"trap_"+(i+1)):definition.keys).filter(k=>!editor?.sessions.some(s=>s.session_key===k));
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
    {editor&&<>
    <div className="manual-session-section">
      {!single&&<div className="manual-session-nav"><h3>{bear?"Trap sessions":"Battle legions"}</h3><div className="manual-session-tabs" role="group" aria-label="Existing sessions">
        {editor.sessions.map(s=><button key={s.id} type="button" className="button button--quiet manual-session-tab" disabled={busy||dirty} aria-pressed={selected===s.id} onClick={()=>{setSelected(s.id);setDraft(s);setConfirmPublish(false);setReview(false);setPaste("");setAddingSession(false)}}>{title(s.session_key)}{bear&&" · "+(hosts.find(a=>a.id===s.host_alliance_id)?.tag??"—")}</button>)}
        {editable&&available.length>0&&editor.sessions.length>0&&<button type="button" className="button button--secondary manual-add-session" disabled={busy||dirty} aria-expanded={addingSession} onClick={()=>setAddingSession(v=>!v)}><Plus size={16}/>Add {sessionNoun}</button>}
      </div></div>}
      {editable&&available.length>0&&(addingSession||!editor.sessions.length)&&<div className="manual-create-session">
        <div className="manual-create-heading"><div><h3>{single?"Initialize results":"New "+sessionNoun}</h3><p>Set the details for the new session.</p></div>{editor.sessions.length>0&&<button type="button" className="button button--quiet" aria-label="Cancel new session" disabled={busy} onClick={()=>setAddingSession(false)}><X size={16}/>Cancel</button>}</div>
        <div className="manual-session-fields">
          {!single&&<label>{bear?"Trap number":"Legion number"}<select aria-label={bear?"Trap number":"Legion number"} value={available.includes(sessionKey)?sessionKey:available[0]} onChange={e=>setSessionKey(e.target.value)} disabled={busy||dirty}>{available.map(k=><option key={k} value={k}>{title(k)}</option>)}</select></label>}
          {bear&&<label>Host alliance<select aria-label="Host alliance" value={host} onChange={e=>setHost(e.target.value)} disabled={busy||dirty}>{hosts.map(a=><option key={a.id} value={a.id}>{a.tag} · {a.name}</option>)}</select></label>}
          <label>Start UTC<input aria-label="Start UTC" type="datetime-local" value={time} onChange={e=>setTime(e.target.value)} disabled={busy||dirty}/></label>
        </div>
        <button type="button" className="button button--primary" disabled={busy||dirty||!time||(bear&&!hosts.some(a=>a.id===host))} onClick={()=>void run(async()=>{const k=available.includes(sessionKey)?sessionKey:available[0];const v=await api.createEventSession(groupId,record.id,k,time+":00Z",bear?host:undefined);apply(v,v.sessions.find(s=>s.session_key===k)?.id)})}>{single?"Initialize results":"Add "+title(available.includes(sessionKey)?sessionKey:available[0])}</button>
      </div>}
      {draft&&<div className="manual-selected-session"><div><h3>{single?"Selected results":title(draft.session_key)}{bear&&" · "+(hosts.find(a=>a.id===draft.host_alliance_id)?.tag??"—")}</h3><p>{draft.started_at.slice(0,16).replace("T"," ")} UTC · {visibleRows.length} players{!loaded&&editable?" · Loading roster…":""}</p></div>
        {editable&&!single&&<button type="button" className="button button--quiet manual-delete-session" disabled={busy||dirty} onClick={()=>{if(window.confirm("Delete this "+title(draft.session_key)+" and all its results?"))void run(async()=>{await api.manageEvent(groupId,record.id,{action:"delete_session",confirmed:true,session_id:draft.id});apply(await api.eventEditor(groupId,record.id))})}}><Trash2 size={15}/>Delete {title(draft.session_key)}</button>}
      </div>}
    </div>
    {draft&&<>{championship&&<div className="manual-review"><h3>Registration summary</h3><p role="status">{champSummary.registered} registered · {champSummary.notRegistered} not registered · {champSummary.unknown} unknown · {champSummary.excused} excused / no duty</p><p>{draft.roster_complete&&draft.registration_complete?"Complete registration list and event roster confirmed.":"Partial registration list — unlisted players remain unknown."}</p>{editable&&<><div className="manual-controls"><label>Registration list<select aria-label="Registration list completeness" value={draft.registration_complete&&draft.roster_complete?"complete":"partial"} disabled={busy||!loaded} onChange={e=>{if(e.target.value==="complete"){setReview(true);setMessage("Enter the game registration count and confirm the event roster below.");}else change(draft)}}><option value="partial">Partial / not yet verified</option><option value="complete">Complete registration list</option></select></label><button type="button" className="button button--secondary" disabled={busy||!loaded} onClick={()=>setReview(true)}>Confirm full registration list</button></div>{review&&<div className="manual-review"><p>Use the total registered shown in the game (not the battle capacity). Verify the roster belongs to the event date, not just today. Mark ineligible players in the table below before confirming.</p><div className="manual-controls"><label>Registered in game<input type="number" min={0} max={500} step={1} value={expectedRegistered} disabled={busy} onChange={e=>{setExpectedRegistered(e.target.value);if(draft.registration_complete)change(draft)}}/></label><label>Players in reviewed roster<input type="number" min={1} max={500} step={1} value={expectedRoster} disabled={busy} onChange={e=>{setExpectedRoster(e.target.value);if(draft.registration_complete)change(draft)}}/></label></div><label><input type="checkbox" disabled={busy} checked={rosterAttested} onChange={e=>setRosterAttested(e.target.checked)}/>I verified this is the complete event-date roster and the full registration list, including any roster exceptions.</label><p>Preview if confirmed: {championshipSummary(visibleRows,true).registered} registered · {championshipSummary(visibleRows,true).notRegistered} not registered · {championshipSummary(visibleRows,true).unknown} unknown · {championshipSummary(visibleRows,true).excused} excused / no duty.</p><button type="button" className="button button--primary" disabled={busy||!loaded||!rosterAttested||expectedRegistered.trim()===""||expectedRoster.trim()===""||!/^\d+$/.test(expectedRegistered)||!/^\d+$/.test(expectedRoster)||Number(expectedRegistered)!==champSummary.registered||Number(expectedRoster)!==visibleRows.length||!visibleRows.length} onClick={()=>{setDraft({...draft,roster_complete:true,registration_complete:true,rows:championshipRows(visibleRows,true)});setDirty(true);setConfirmPublish(false);setRosterAttested(false);setMessage("Full list confirmed. Save draft before publishing.");}}>Confirm and mark unregistered</button></div>}</>}</div>}
    {editable&&<><div className="manual-player-tools">
      <h3>Player tools</h3><div className="manual-session-fields"><label>Find player<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name or ID"/></label>
      <label>Sort<select aria-label="Sort" value={sort} onChange={e=>setSort(e.target.value)}><option value="nickname">Name</option>{definition.metrics.map(([key,label])=><option key={key} value={key}>{label} (highest first)</option>)}</select></label></div>
      {definition.registration&&<div className="manual-bulk-actions"><button className="button button--quiet" disabled={busy||!loaded} onClick={()=>bulk(true)}>Register all</button><button className="button button--quiet" disabled={busy||!loaded} onClick={()=>bulk(false)}>Clear registrations</button><span>{visibleRows.filter(r=>r.registration==="registered").length} registered</span></div>}
    </div>
    {foundry?<div className="manual-review"><h3>Foundry evidence</h3><div className="manual-controls" role="group" aria-label="Foundry import stage"><button type="button" className="button button--secondary" aria-pressed={foundryStage==="registration"} disabled={busy} onClick={()=>setFoundryStage("registration")}>Registration{draft.registration_complete?" · Reviewed":""}</button><button type="button" className="button button--secondary" aria-pressed={foundryStage==="results"} disabled={busy} onClick={()=>setFoundryStage("results")}>Battle results{draft.results_complete?" · Reviewed":""}</button></div><p>Save the registration as a draft on Thursday or import both stages on Sunday. Each legion is reviewed independently.</p>
    <div hidden={foundryStage!=="registration"}><ScreenshotImport key={draft.id+":registration"} groupId={groupId} eventId={record.id} sessionId={draft.id} disabled={busy||!loaded||dirty||foundryStage!=="registration"} onBusy={setBusy} eventType="foundry_registration" sessionKey={draft.session_key} players={candidates} onImport={(rows,info)=>importOcr(rows,info,"registration")}/>
    <div className="manual-controls">{(["main_count","substitute_count"] as const).map(k=><label key={k}>{k==="main_count"?"Combatants in mail":"Substitutes in mail"}<input type="number" min={0} max={k==="main_count"?30:10} step={1} disabled={busy} value={draft.foundry_details?.[k]??""} onChange={e=>change({...draft,registration_complete:false,foundry_details:{...draft.foundry_details,[k]:e.target.value===""?undefined:Number(e.target.value)}})}/></label>)}</div>
    <p>{visibleRows.filter(r=>r.registration==="registered"&&r.role==="main").length} main · {visibleRows.filter(r=>r.registration==="registered"&&r.role==="substitute").length} substitutes · {visibleRows.filter(r=>r.registration==="registered"&&!r.role).length} unresolved roles</p>
    <label><input type="checkbox" checked={!!draft.registration_complete} disabled={busy||draft.foundry_details?.main_count==null||draft.foundry_details?.substitute_count==null||draft.foundry_details.main_count!==visibleRows.filter(r=>r.registration==="registered"&&r.role==="main").length||draft.foundry_details.substitute_count!==visibleRows.filter(r=>r.registration==="registered"&&r.role==="substitute").length||visibleRows.some(r=>r.registration==="registered"&&!r.role)} onChange={e=>complete("registration_complete",e.target.checked)}/>I verified the full combatant and substitute lists against the mail counts.</label></div>
    <div hidden={foundryStage!=="results"}><ScreenshotImport key={draft.id+":results"} groupId={groupId} eventId={record.id} sessionId={draft.id} disabled={busy||!loaded||dirty||foundryStage!=="results"} onBusy={setBusy} eventType="foundry_results" sessionKey={draft.session_key} players={candidates} onImport={(rows,info)=>importOcr(rows,info,"results")}/>
    <div className="manual-controls"><label>Battle outcome<select value={draft.foundry_details?.outcome??""} disabled={busy} onChange={e=>change({...draft,foundry_details:{...draft.foundry_details,outcome:(e.target.value||undefined) as FoundryImportInfo["outcome"]}})}><option value="">Unknown</option><option value="victory">Victory</option><option value="defeat">Defeat</option></select></label>{(["own_score","opponent_score","opponent_state","opponent_tag","opponent_name"] as const).map(k=><label key={k}>{k.replaceAll("_"," ")}<input type={k.endsWith("_score")?"number":"text"} min={0} value={draft.foundry_details?.[k]??""} disabled={busy} onChange={e=>change({...draft,foundry_details:{...draft.foundry_details,[k]:e.target.value===""?undefined:k.endsWith("_score")?Number(e.target.value):e.target.value}})}/></label>)}</div>
    <p>{visibleRows.filter(r=>(r.metrics.personal_points??0)>0).length} positive · {visibleRows.filter(r=>r.metrics.personal_points===0).length} explicit zero · {visibleRows.filter(r=>r.registration==="registered"&&r.metrics.personal_points===undefined).length} selected without results · {visibleRows.filter(r=>r.registration!=="registered"&&r.metrics.personal_points!==undefined).length} results without registration</p>
    <label><input type="checkbox" checked={!!draft.results_complete} disabled={busy||visibleRows.some(r=>r.registration!=="registered"&&r.metrics.personal_points!==undefined)} onChange={e=>complete("results_complete",e.target.checked)}/>I verified the full personal points list and reviewed the battle outcome. Zero is a no-show for selected players; missing points are not zero.</label></div>
    <button className="button button--primary" disabled={busy||!loaded} onClick={()=>void run(save)}>Save reviewed {foundryStage==="registration"?"registration":"results"} draft</button></div>:<ScreenshotImport key={groupId+":"+record.id+":"+draft.id} groupId={groupId} eventId={record.id} sessionId={draft.id} disabled={busy||!loaded||dirty} onBusy={setBusy} eventType={record.event_type} sessionKey={draft.session_key} players={candidates} onImport={importOcr} />}
    <div className="manual-import">
      <div className="manual-import-heading"><h3>Paste a list</h3><p className="manual-help">Import a text or spreadsheet list into the selected session.</p></div>
      {definition.battle&&<label>List type<select value={pasteKind} onChange={e=>setPasteKind(e.target.value)}><option value="registration">Registered players</option><option value="main">Main players</option><option value="substitute">Substitutes</option><option value="metrics">Personal points</option></select></label>}
      <p className="manual-help">{definition.registration&&(!definition.battle||pasteKind!=="metrics")?"One player name or ID per line.":"Paste spreadsheet columns separated by tabs: player name or ID, "+definition.metrics.map(c=>c[1]).join(", ")+". "} Exact matches only; ambiguous names require ID. No changes are applied if any line fails.</p>
      <textarea aria-label="Paste player list" rows={4} value={paste} onChange={e=>setPaste(e.target.value)} placeholder="Paste here…"/>
      <button className="button button--secondary" disabled={busy||!loaded||!paste.trim()} onClick={importPaste}>Import list</button>
    </div>
    {query.trim()&&<div className="manual-controls">{candidates.filter(p=>!visibleRows.some(r=>r.fid===p.fid)&&((p.nickname??"")+" "+p.fid).toLowerCase().includes(query.toLowerCase())).slice(0,15).map(p=><button className="button button--quiet" key={p.fid} disabled={busy} onClick={()=>add(p)}>Add {p.nickname??p.fid}</button>)}</div>}
    </>}
    <div className="table-wrap"><table><thead><tr><th>Player / ID</th>{definition.registration&&<th>Registered</th>}{definition.battle&&<th>Role</th>}{definition.attendance&&(definition.battle||review||!editable)&&<th>Attendance</th>}{definition.metrics.map(([k,l])=><th key={k}>{l}</th>)}{editable&&review&&<th>Roster exception</th>}</tr></thead><tbody>
    {visibleRows.filter(r=>!query.trim()|| (r.nickname+" "+r.fid).toLowerCase().includes(query.toLowerCase())).sort((a,b)=>sort==="nickname"?a.nickname.localeCompare(b.nickname):(b.metrics[sort]??-1)-(a.metrics[sort]??-1)).map(row=><tr key={row.fid}><td>{row.nickname}<small className="table-subline mono">{row.fid}</small></td>
    {definition.registration&&<td><input type="checkbox" aria-label={row.nickname+" Registered"} checked={row.registration==="registered"} disabled={!editable||busy} onChange={e=>patchVisible(row.fid,regPatch(row,e.target.checked))}/>{championship?(row.eligibility==="no_duty"||row.registration==="excused"?" Excused / no duty":row.registration==="registered"?" Registered":row.registration==="not_registered"?" Not registered":" Unknown"):row.registration==="unknown"&&!editable?" Unknown":row.registration==="excused"?" Excused":""}</td>}
    {definition.battle&&<td>{selectField(row,"role")}</td>}
    {definition.attendance&&(definition.battle||review||!editable)&&<td>{selectField(row,"attendance")}</td>}
    {definition.metrics.map(([key,label])=><td key={key}><input type="number" min={0} max={Number.MAX_SAFE_INTEGER} step={1} aria-label={row.nickname+" "+label} disabled={!editable||busy} value={row.metrics[key]??""} onChange={e=>{const next=metricPatch(row,key,e.target.value);if(definition.attendance&&Number(e.target.value)>0)next.attendance="confirmed_present";patchVisible(row.fid,next)}}/></td>)}
    {editable&&review&&<td><label><input type="checkbox" checked={row.eligibility==="no_duty"} disabled={busy} onChange={e=>patchVisible(row.fid,{eligibility:e.target.checked?"no_duty":draft.roster_complete?"confirmed":"unknown",registration:championship&&row.eligibility==="no_duty"&&!e.target.checked&&row.registration==="excused"?"unknown":championship&&e.target.checked&&row.registration==="registered"?"excused":row.registration==="not_registered"?"unknown":row.registration,registered_by:championship&&e.target.checked?null:row.registered_by,attendance:row.attendance==="confirmed_absent"?"unknown":row.attendance})}/>Not eligible</label></td>}
    </tr>)}
    </tbody></table></div>
    {editable&&<><div className="manual-controls"><button className="button button--primary" disabled={busy||!loaded||(!dirty&&draft.rows.length===0&&visibleRows.length===0)} onClick={()=>void run(save)}>Save draft</button><button className="button button--secondary" disabled={busy||!loaded} onClick={()=>setReview(v=>!v)}>Review completeness</button>{dirty&&<span>Unsaved changes</span>}</div>
    {review&&!championship&&<div className="manual-review"><h3>Review before publishing</h3><p>Leave unchecked if the information is partial. Missing entries remain unknown.</p>
    <label><input type="checkbox" checked={!!draft.roster_complete} onChange={e=>confirmRoster(e.target.checked)}/>This is the full alliance roster at the time of the event (mark exceptions in the table).</label>
    {definition.registration&&<label><input type="checkbox" checked={!!draft.registration_complete} onChange={e=>complete("registration_complete",e.target.checked)}/>I entered the complete registration list.</label>}
    {definition.attendance&&<label><input type="checkbox" checked={!!draft.attendance_complete} onChange={e=>complete("attendance_complete",e.target.checked)}/>{record.event_type==="foundry"?"Review personal points; explicit zero means no-show for a selected player.":"I verified who actually attended, not just who scored points. Use Final attendance review to calculate absences automatically."}</label>}
    {(record.event_type==="foundry"||!definition.registration&&!definition.attendance)&&<label><input type="checkbox" checked={!!draft.results_complete} onChange={e=>complete("results_complete",e.target.checked)}/>I entered the full results list.</label>}
    <p>Partial records remain unknown. Final attendance review can calculate absences from a confirmed complete roster and attendance list.</p>
    <button className="button button--primary" disabled={busy} onClick={()=>void run(save)}>Save reviewed draft</button></div>}</>}
    </>}
    {editable&&loaded&&(!bear||hosts.length>0)&&definition.attendance&&editor.sessions.length>0&&<AttendanceFinalReview key={editor.sessions.map(s=>s.id+":"+s.revision).join("|")} event={editor} candidates={candidates} alliances={hosts} allianceId={record.alliance_id} occurredOn={record.occurred_on} disabled={busy||dirty||!loaded} onPublish={completion=>void run(async()=>{apply(await api.publishEvent(groupId,record.id,false,completion),selected);onPublished();setMessage("Event published with automatic attendance.")})}/>}
    {editable&&editor.sessions.length>0&&<div className="manual-controls">{record.event_type==="bear_trap"&&<label><input type="checkbox" checked={cycleComplete} disabled={dirty||busy} onChange={e=>setCycleComplete(e.target.checked)}/>Legacy manual attendance confirmation (optional). Use Final attendance review for automatic absences.</label>}<label><input type="checkbox" checked={confirmPublish} disabled={dirty||busy} onChange={e=>setConfirmPublish(e.target.checked)}/>I reviewed all recorded sessions (partial publication; no automatic absences)</label><button className="button button--secondary" disabled={busy||dirty||!confirmPublish} onClick={()=>void run(async()=>{apply(await api.publishEvent(groupId,record.id,cycleComplete),selected);setConfirmPublish(false);onPublished();setMessage("Event published.")})}>{definition.attendance?"Publish partial results":"Publish event"}</button></div>}
    </>}
  </section>;
}
