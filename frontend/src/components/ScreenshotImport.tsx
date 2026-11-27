import { useEffect, useRef, useState } from "react";
import { ImagePlus } from "lucide-react";
import { api, type OcrPreview } from "../lib/api";
import { parseScreenshot, normalizeName, type FoundryImportInfo } from "../lib/ocrParser";
import { matchPlayer, rankedPlayers } from "../lib/ocrMatching";
import { summarizeReview, type ReviewRow } from "../lib/ocrReview";
import type { Player } from "../lib/types";

type Item = { id: number; file: File; status: "pending" | "running" | "done" | "error"; result?: OcrPreview; error?: string };
const MAX_FILES = 30;
const MAX_SOURCE_BYTES = 20 * 1024 * 1024;

async function prepare(file: File, limit: number): Promise<Blob> {
  if (file.size > MAX_SOURCE_BYTES) throw new Error("Original image exceeds 20 MiB.");
  if (!["image/png", "image/jpeg"].includes(file.type)) throw new Error("Choose PNG or JPEG screenshots.");
  if (file.size <= limit) return file;
  const bitmap = await createImageBitmap(file);
  try {
    if (bitmap.width * bitmap.height > 24_000_000) throw new Error("Image resolution is too large.");
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d");
    if (!context) throw new Error("Image preparation is unavailable.");
    for (const scale of [1, .9, .8]) {
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      context.fillStyle = "#fff";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      for (const quality of [.95, .85, .75]) {
        const blob = await new Promise<Blob | null>(resolve => canvas.toBlob(resolve, "image/jpeg", quality));
        if (blob && blob.size <= limit) return blob;
      }
    }
    throw new Error("Screenshot is too large. Crop it to the relevant table and retry.");
  } finally { bitmap.close(); }
}

export function ScreenshotImport({groupId,eventId,sessionId,disabled,onBusy,eventType,sessionKey,players,onImport}:{groupId:string;eventId:string;sessionId:string;disabled:boolean;onBusy:(busy:boolean)=>void;eventType:string;sessionKey:string;players:Player[];onImport:(rows:ReviewRow[],info?:FoundryImportInfo)=>Promise<void>}) {
  const [config,setConfig]=useState<{configured:boolean;max_image_bytes:number}|null>(null);
  const [error,setError]=useState("");
  const [items,setItems]=useState<Item[]>([]);
  const [running,setRunning]=useState(false);
  const nextId=useRef(0);
  const fileInput=useRef<HTMLInputElement>(null);
  const active=useRef(true);
  const stop=useRef(false);
  useEffect(()=>{
    active.current=true;
    api.ocrStatus().then(v=>{if(active.current)setConfig(v)}).catch(e=>{if(active.current)setError(String(e.message))});
    return ()=>{active.current=false;stop.current=true};
  },[]);
  useEffect(()=>{
    if(!running&&!items.length)return;
    const handler=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue=""};
    window.addEventListener("beforeunload",handler);
    return ()=>window.removeEventListener("beforeunload",handler);
  },[running,items.length]);
  const patch=(id:number,value:Partial<Item>)=>{if(active.current)setItems(old=>old.map(item=>item.id===id?{...item,...value}:item))};
  const recognize=async()=>{
    if(!config?.configured||running||disabled)return;
    setRunning(true);onBusy(true);stop.current=false;setError("");setReviewRows([]);setParseWarnings([]);
    try {
      for(const item of items.filter(i=>i.status==="pending"||i.status==="error")){
        if(stop.current||!active.current)break;
        patch(item.id,{status:"running",error:undefined});
        try {
          const image=await prepare(item.file,config.max_image_bytes);
          if(stop.current||!active.current){patch(item.id,{status:"pending"});break}
          const result=await api.ocrPreview(groupId,eventId,sessionId,image);
          patch(item.id,{status:"done",result});
        }catch(e){patch(item.id,{status:"error",error:e instanceof Error?e.message:"Recognition failed"})}
      }
    }finally{if(active.current){setRunning(false);onBusy(false)}}
  };
  const [reviewRows,setReviewRows]=useState<ReviewRow[]>([]);
  const [parseWarnings,setParseWarnings]=useState<string[]>([]);
  const mobilization=eventType==="alliance_mobilization";
  const foundryReg=eventType==="foundry_registration",foundryResults=eventType==="foundry_results";
  const [foundryInfo,setFoundryInfo]=useState<FoundryImportInfo>({});
  const supported=eventType==="bear_trap"||eventType==="alliance_championship"||mobilization||foundryReg||foundryResults;
  const buildReview=()=>{
    const parsed=items.flatMap(i=>i.result?[{file:i.file.name,...parseScreenshot(i.result,eventType,sessionKey,i.file.name)}]:[]);
    const unique=new Map<string,typeof reviewRows[number]>();
    const metadata:Record<string,string|number>={},conflicting=new Set<string>();
    for(const page of parsed)for(const [k,v] of Object.entries(page.foundry??{})){
      if(v===undefined)continue;
      if(k in metadata&&metadata[k]!==v)conflicting.add(k);else metadata[k]=v;
    }
    for(const k of conflicting)delete metadata[k];
    setFoundryInfo(metadata as FoundryImportInfo);
    const knownRoles=new Map<string,Set<"main"|"substitute">>();
    for(const page of parsed)for(const r of page.rows){if(r.role){const k=normalizeName(r.nickname);const roles=knownRoles.get(k)??new Set();roles.add(r.role);knownRoles.set(k,roles)}}
    const batchRows=parsed.flatMap(page=>{
      if(!foundryReg)return page.rows;
      const overlap=new Set(page.rows.flatMap(r=>[...(knownRoles.get(normalizeName(r.nickname))??[])]));
      return page.rows.map(r=>{const direct=knownRoles.get(normalizeName(r.nickname));const role=direct?.size===1?[...direct][0]:!page.rows.some(v=>v.role)&&overlap.size===1?[...overlap][0]:undefined;return r.role||!role?r:{...r,role}});
    });
    for(const row of batchRows){
      const match=matchPlayer(row.nickname,players);
      const key=normalizeName(row.nickname)+":"+JSON.stringify([row.damage,row.completed,row.total,row.points,row.role,row.rank]);
      if(!unique.has(key))unique.set(key,{...row,...match,include:true});
    }
    setReviewRows([...unique.values()]);setParseWarnings([...parsed.flatMap(p=>p.warnings.map(w=>p.file+": "+w)),...Array.from(conflicting,k=>"Conflicting screenshot metadata: "+k+"; verify and enter it manually.")]);
  };
  const selected=reviewRows.filter(r=>r.include);
  const summary=summarizeReview(reviewRows,eventType);
  const conflict=summary.conflicts.size>0;
  const ordered=reviewRows.map((r,i)=>({r,i})).sort((a,b)=>{
    const priority=(r:ReviewRow)=>!r.include?4:summary.conflicts.has(r.fid)?0:r.match==="unknown"?1:r.match==="suggested"?2:3;
    return priority(a.r)-priority(b.r)||a.i-b.i;
  });
  const [imported,setImported]=useState(0);
  const importResults=async()=>{
    if(disabled||running||summary.conflicts.size||!summary.rows.length||selected.some(r=>!r.fid||r.match==="suggested"||r.match==="unknown"))return;
    setError("");setRunning(true);
    try{await onImport(summary.rows,foundryReg||foundryResults?foundryInfo:undefined);if(active.current){setImported(summary.rows.length);setReviewRows([]);setItems([]);setParseWarnings([])}}
    catch(e){if(active.current)setError(e instanceof Error?e.message:"Import failed")}
    finally{if(active.current)setRunning(false)}
  };
  const done=items.filter(i=>i.status==="done").length;
  return <div className="manual-import ocr-import">
    <div className="manual-import-heading"><h3>{foundryReg?"Import registration screenshots":foundryResults?"Import battle result screenshots":"Import screenshots (OCR preview)"}</h3><p className="manual-help">{foundryReg?"Upload registration mail or final in-game Combatants lists for the selected legion. Keep the legion header, counts and Participants only footer visible.":"Upload screenshots for the selected session."}</p></div>
    {!supported&&<p className="manual-help">Automatic table parsing for this event is not available yet.</p>}
    <p className="manual-help">Select screenshots from this session. Images are sent to Google Vision one at a time. This preview does not change player results or publish the event.</p>
    {imported>0&&<p role="status">Imported and saved {imported} players. Event remains a draft.</p>}
    {error&&<p role="alert">{error}</p>}
    {config&&!config.configured&&<p className="manual-help">Google Vision is not configured on the server.</p>}
    {config?.configured&&<>
      <div className="ocr-upload"><input ref={fileInput} className="ocr-native-file" aria-label="Choose screenshots" type="file" accept="image/png,image/jpeg" multiple disabled={disabled||running} onChange={e=>{
        const files=Array.from(e.target.files??[]);e.target.value="";
        if(items.length+files.length>MAX_FILES){setError("Choose at most 30 screenshots per batch.");return}
        setError("");setImported(0);setReviewRows([]);setParseWarnings([]);setItems(old=>[...old,...files.map(file=>({id:++nextId.current,file,status:"pending" as const}))]);
      }}/><button type="button" className="button button--secondary ocr-upload-button" disabled={disabled||running} onClick={()=>fileInput.current?.click()}><ImagePlus size={20}/>{foundryReg?"Upload registration screenshots":foundryResults?"Upload battle result screenshots":"Upload screenshots"}</button><div className="ocr-upload-caption"><strong role="status">{items.length?items.length+" screenshots selected":"No screenshots selected"}</strong><small>PNG or JPEG · up to 30 images per batch</small></div></div>
      {items.length>0&&<>
        <p className="manual-help" role="status">{done} of {items.length} screenshots recognized</p>
        <div className="manual-controls ocr-actions">
          <button type="button" className="button button--primary" disabled={disabled||running||items.every(i=>i.status==="done")} onClick={()=>void recognize()}>Recognize screenshots</button>
          {running&&<button type="button" className="button button--secondary" onClick={()=>{stop.current=true}}>Stop after current image</button>}
          <button type="button" className="button button--quiet" disabled={running||disabled} onClick={()=>{setItems([]);setReviewRows([]);setParseWarnings([])}}>Clear screenshots</button>
        </div>
        {supported&&done>0&&<button className="button button--secondary" disabled={running||disabled} onClick={buildReview}>Review recognized players</button>}
        {parseWarnings.length>0&&<details><summary>Recognition warnings ({parseWarnings.length})</summary>{parseWarnings.map((w,i)=><p key={i}>{w}</p>)}</details>}
        {reviewRows.length>0&&<>{(foundryReg||foundryResults)&&<p className="manual-help">{Object.entries(foundryInfo).filter(([,v])=>v!==undefined).map(([k,v])=>k.replaceAll("_"," ")+": "+v).join(" · ")||"No complete screenshot header detected; verify metadata manually."}</p>}{foundryReg&&reviewRows.some(r=>!r.role)&&<div className="manual-controls"><button type="button" className="button button--quiet" onClick={()=>setReviewRows(old=>old.map(r=>r.role?r:{...r,role:"main"}))}>Assign unresolved as main</button><button type="button" className="button button--quiet" onClick={()=>setReviewRows(old=>old.map(r=>r.role?r:{...r,role:"substitute"}))}>Assign unresolved as substitute</button></div>}<p role="status">{reviewRows.length} distinct recognized rows · {reviewRows.filter(r=>r.match==="unknown").length} unresolved · {reviewRows.filter(r=>r.match==="suggested").length} suggested · {summary.rows.length} matched unique players (including unconfirmed suggestions).</p><p className="manual-help">Yellow player selectors indicate suggested matches; red selectors indicate unresolved players. Check them against the screenshot; confirm suggestions by selecting a player or using Confirm suggested matches.</p><div className="table-wrap"><table><thead><tr><th>Include</th><th>Detected name / source</th><th>Player</th>{eventType==="bear_trap"&&<th>Damage</th>}{mobilization&&<><th>Missions</th><th>Points</th></>}{foundryReg&&<th>Role</th>}{foundryResults&&<><th>Rank</th><th>Personal points</th></>}</tr></thead><tbody>{ordered.map(({r,i})=><tr key={i} className={r.include&&summary.conflicts.has(r.fid)?"ocr-conflict-row":""}><td><input type="checkbox" aria-label={"Include "+r.nickname} checked={r.include} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,include:e.target.checked}:v))}/></td><td>{r.nickname}<small className="table-subline">{r.source}</small>{r.include&&summary.conflicts.has(r.fid)&&<small className="ocr-conflict-label">Conflicting results — keep one or correct values</small>}</td><td><select className={r.match==="suggested"?"ocr-match-warning":r.match==="unknown"?"ocr-match-unresolved":""} aria-label={"Match "+r.nickname} title={r.match==="suggested"?"Suggested match — verify":r.match==="unknown"?"No reliable match": "Confirmed match"} value={r.fid} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,fid:e.target.value,match:e.target.value?"manual":"unknown"}:v))}><option value="">Choose player</option>{rankedPlayers(r.nickname,players).map(p=><option key={p.fid} value={p.fid}>{p.nickname??p.fid} · {p.fid}</option>)}</select></td>{eventType==="bear_trap"&&<td><input aria-label={"Damage for "+r.nickname} type="number" min={1} value={r.damage??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,damage:e.target.value?Number(e.target.value):undefined}:v))}/></td>}{foundryReg&&<td><select aria-label={"Role for "+r.nickname} value={r.role??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,role:(e.target.value||undefined) as ReviewRow["role"]}:v))}><option value="">Confirm role</option><option value="main">Main</option><option value="substitute">Substitute</option></select></td>}{foundryResults&&<><td><input aria-label={"Rank for "+r.nickname} type="number" min={1} max={40} value={r.rank??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,rank:e.target.value===""?undefined:Number(e.target.value)}:v))}/></td><td><input aria-label={"Points for "+r.nickname} type="number" min={0} value={r.points??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,points:e.target.value===""?undefined:Number(e.target.value)}:v))}/></td></>}{mobilization&&<><td><input aria-label={"Completed for "+r.nickname} type="number" min={0} value={r.completed??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,completed:e.target.value===""?undefined:Number(e.target.value)}:v))}/> / {r.total??"—"}</td><td><input aria-label={"Points for "+r.nickname} type="number" min={0} value={r.points??""} onChange={e=>setReviewRows(old=>old.map((v,j)=>i===j?{...v,points:e.target.value===""?undefined:Number(e.target.value)}:v))}/></td></>}</tr>)}</tbody></table></div>{selected.some(r=>r.match==="suggested")&&<button type="button" className="button button--secondary" disabled={disabled||running} onClick={()=>{if(window.confirm("Have you checked all included suggested player matches?"))setReviewRows(old=>old.map(r=>r.include&&r.match==="suggested"?{...r,match:"manual"}:r))}}>Confirm suggested matches</button>}{summary.duplicates>0&&<p role="status">{summary.duplicates} duplicate records will be merged automatically.</p>}{conflict&&<div role="alert" className="notice notice--error">Conflicting results: {[...summary.conflicts].map(fid=>players.find(p=>p.fid===fid)?.nickname??fid).join(", ")}. These rows are at the top of the table.</div>}<button className="button button--primary" disabled={disabled||running||!selected.length||conflict||selected.some(r=>!r.fid||r.match==="suggested"||r.match==="unknown"||(eventType==="bear_trap"&&(!Number.isSafeInteger(r.damage)||!r.damage||r.damage<1))||(foundryReg&&!r.role)||(foundryResults&&(!Number.isSafeInteger(r.points)||(r.points??-1)<0||(r.rank!==undefined&&(!Number.isInteger(r.rank)||r.rank<1||r.rank>40))))||(mobilization&&(!Number.isSafeInteger(r.completed)||!Number.isSafeInteger(r.points)||(r.completed??-1)<0||(r.points??-1)<0||(r.completed??0)>(r.total??-1))))} onClick={()=>void importResults()}>Import results</button></>}
        {items.map(item=><div className="ocr-preview-item" key={item.id}>
          <div className="ocr-preview-heading"><strong>{item.file.name}</strong><span>{item.status}</span><button type="button" className="button button--quiet" disabled={running||disabled} onClick={()=>{setItems(old=>old.filter(i=>i.id!==item.id));setReviewRows([]);setParseWarnings([])}}>Remove</button></div>
          {item.error&&<p className="notice notice--error">{item.error}</p>}
          {item.result&&<details><summary>Recognized text ({item.result.tokens.length} words)</summary><textarea aria-label={"OCR text "+item.file.name} readOnly rows={5} value={item.result.text}/><details><summary>Debug word coordinates</summary><textarea aria-label={"OCR coordinates "+item.file.name} readOnly rows={5} value={JSON.stringify(item.result.tokens)}/></details>{item.result.warnings.length>0&&<p>{item.result.warnings.join(", ")}</p>}</details>}
        </div>)}
      </>}
    </>}
  </div>;
}
