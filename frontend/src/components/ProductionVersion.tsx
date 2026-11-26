import { useEffect, useState } from "react";
import { versionState } from "../lib/version";

declare const __VZN_BUILD_SHA__: string | null;
const build = __VZN_BUILD_SHA__;
const repo = "https://github.com/FawLog/vzn-activity-tracker";

export function ProductionVersion(){
  const [server,setServer]=useState<string|null>(null);
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    const check=async()=>{
      setLoading(true);
      try{
        const response=await fetch("/api/v1/version",{cache:"no-store",credentials:"same-origin",signal:controller.signal});
        if(!response.ok)throw new Error("Version unavailable");
        const body=await response.json();
        if(!controller.signal.aborted)setServer(typeof body.sha==="string"&&/^[0-9a-f]{40}$/.test(body.sha)?body.sha:null);
      }catch{if(!controller.signal.aborted)setServer(null)}
      finally{if(!controller.signal.aborted)setLoading(false)}
    };
    void check();
    const onFocus=()=>{if(document.visibilityState==="visible")void check()};
    window.addEventListener("focus",onFocus);
    document.addEventListener("visibilitychange",onFocus);
    return()=>{controller.abort();window.removeEventListener("focus",onFocus);document.removeEventListener("visibilitychange",onFocus)};
  },[revision]);
  const state=versionState(build,server,loading);
  return <span className="production-version">
    <span>Production <code title={server??undefined}>{server?.slice(0,7)??"—"}</code></span>
    {build&&<span title={build}>UI <code>{build.slice(0,7)}</code></span>}
    <span className={"version-"+state.kind} aria-live="polite">{state.label}</span>
    {state.kind==="stale"&&<button type="button" onClick={()=>window.location.reload()}>Reload</button>}
    <button type="button" onClick={()=>setRevision(n=>n+1)}>Check</button>
    <a href={repo+"/actions/workflows/ci.yml?query=branch%3Amain"} target="_blank" rel="noopener noreferrer">Latest CI ↗</a>
  </span>;
}
