import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { versionState, validSha, type RepositoryVersion } from "../lib/version";

declare const __VZN_BUILD_SHA__: string | null;
const build = __VZN_BUILD_SHA__;
const repo = "https://github.com/FawLog/vzn-activity-tracker";

async function getJson(path:string,signal:AbortSignal){
  const response=await fetch(path,{cache:"no-store",credentials:"same-origin",signal});
  if(!response.ok)throw new Error("Version unavailable");
  return response.json();
}
export function ProductionVersion(){
  const [server,setServer]=useState<string|null>(null);
  const [remote,setRemote]=useState<RepositoryVersion|null>(null);
  const [loading,setLoading]=useState(true);
  const [revision,setRevision]=useState(0);
  useEffect(()=>{
    const controller=new AbortController();
    let running=false;
    const check=async()=>{
      if(running)return;
      running=true;
      setLoading(true);
      const [local,latest]=await Promise.allSettled([
        getJson("/api/v1/version",controller.signal),
        getJson("/api/v1/repository-version",controller.signal)
      ]);
      if(!controller.signal.aborted){
        setServer(local.status==="fulfilled"?validSha(local.value.sha):null);
        const body=latest.status==="fulfilled"?latest.value:null;
        setRemote(body&&validSha(body.sha)?{sha:body.sha,ci:body.ci,checked_at:body.checked_at}:null);
        setLoading(false);
      }
      running=false;
    };
    void check();
    const onFocus=()=>{if(document.visibilityState==="visible")void check()};
    window.addEventListener("focus",onFocus);
    document.addEventListener("visibilitychange",onFocus);
    return()=>{controller.abort();window.removeEventListener("focus",onFocus);document.removeEventListener("visibilitychange",onFocus)};
  },[revision]);
  const state=versionState(build,server,remote,loading);
  const checked=remote?.checked_at?new Date(remote.checked_at):null;
  return <span className="production-version">
    <span>GitHub <code title={remote?.sha}>{remote?.sha.slice(0,7)??"—"}</code></span>
    <span>Production <code title={server??undefined}>{server?.slice(0,7)??"—"}</code></span>
    {build&&<span title={build}>UI <code>{build.slice(0,7)}</code></span>}
    <span className={"version-"+state.kind} aria-live="polite" title={checked&&!Number.isNaN(checked.getTime())?"GitHub checked "+checked.toLocaleString():undefined}>{state.label}</span>
    {build&&server&&build!==server&&<button type="button" onClick={()=>window.location.reload()}>Reload page</button>}
    <button className="version-refresh" type="button" aria-label="Refresh version status" title="Refresh version status" disabled={loading} onClick={()=>setRevision(n=>n+1)}><RefreshCw size={16} aria-hidden="true" className={loading?"version-spinning":undefined}/></button>
    <a href={repo+"/actions/workflows/ci.yml?query=branch%3Amain"} target="_blank" rel="noopener noreferrer">CI ↗</a>
  </span>;
}
