import { useEffect, useRef, useState } from "react";
import { api, type OcrPreview } from "../lib/api";

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

export function ScreenshotImport({groupId,eventId,sessionId,disabled,onBusy}:{groupId:string;eventId:string;sessionId:string;disabled:boolean;onBusy:(busy:boolean)=>void}) {
  const [config,setConfig]=useState<{configured:boolean;max_image_bytes:number}|null>(null);
  const [error,setError]=useState("");
  const [items,setItems]=useState<Item[]>([]);
  const [running,setRunning]=useState(false);
  const nextId=useRef(0);
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
    setRunning(true);onBusy(true);stop.current=false;setError("");
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
  const done=items.filter(i=>i.status==="done").length;
  return <div className="manual-import ocr-import">
    <h3>Import screenshots (OCR preview)</h3>
    <p className="manual-help">Select screenshots from this session. Images are sent to Google Vision one at a time. This preview does not change player results or publish the event.</p>
    {error&&<p role="alert">{error}</p>}
    {config&&!config.configured&&<p className="manual-help">Google Vision is not configured on the server.</p>}
    {config?.configured&&<>
      <label>Choose screenshots<input aria-label="Choose screenshots" type="file" accept="image/png,image/jpeg" multiple disabled={disabled||running} onChange={e=>{
        const files=Array.from(e.target.files??[]);e.target.value="";
        if(items.length+files.length>MAX_FILES){setError("Choose at most 30 screenshots per batch.");return}
        setError("");setItems(old=>[...old,...files.map(file=>({id:++nextId.current,file,status:"pending" as const}))]);
      }}/></label>
      {items.length>0&&<>
        <p className="manual-help" role="status">{done} of {items.length} screenshots recognized</p>
        <div className="manual-controls">
          <button type="button" className="button button--primary" disabled={disabled||running||items.every(i=>i.status==="done")} onClick={()=>void recognize()}>Recognize screenshots</button>
          {running&&<button type="button" className="button button--secondary" onClick={()=>{stop.current=true}}>Stop after current image</button>}
          <button type="button" className="button button--quiet" disabled={running||disabled} onClick={()=>setItems([])}>Clear screenshots</button>
        </div>
        {items.map(item=><div className="ocr-preview-item" key={item.id}>
          <div className="ocr-preview-heading"><strong>{item.file.name}</strong><span>{item.status}</span><button type="button" className="button button--quiet" disabled={running||disabled} onClick={()=>setItems(old=>old.filter(i=>i.id!==item.id))}>Remove</button></div>
          {item.error&&<p className="notice notice--error">{item.error}</p>}
          {item.result&&<details><summary>Recognized text ({item.result.tokens.length} words)</summary><textarea aria-label={"OCR text "+item.file.name} readOnly rows={5} value={item.result.text}/>{item.result.warnings.length>0&&<p>{item.result.warnings.join(", ")}</p>}</details>}
        </div>)}
      </>}
    </>}
  </div>;
}
