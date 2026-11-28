import {useRef,useState} from "react";
import {api} from "../lib/api";
import type {CalendarOccurrence} from "../lib/calendar";
import {allowNavigation,useNavigationGuard} from "../lib/navigation-guard";

export function FollowScheduleDetails({groupId,row,writable,onStopped}:{groupId:string;row:CalendarOccurrence;writable:boolean;onStopped:()=>void}){
  const [busy,setBusy]=useState(false);
  const [error,setError]=useState("");
  const lock=useRef(false);
  useNavigationGuard(false,busy);
  async function stop(){
    if(lock.current||!row.follow_rule_id||!allowNavigation()||!window.confirm("Stop following the parent? Past and already-started dates remain visible."))return;
    lock.current=true;setBusy(true);setError("");
    try{await api.stopFollow(groupId,row.follow_rule_id);onStopped();}
    catch(e){setError(e instanceof Error?e.message:"Unable to stop following");}
    finally{lock.current=false;setBusy(false);}
  }
  return <section aria-label="Parent schedule"><p>Follows {row.follow_parent_label}. Change dates in the parent schedule; this event updates automatically.</p>
    {writable&&row.follow_active&&<button type="button" className="button button--quiet" disabled={busy} onClick={()=>void stop()}>Stop following</button>}
    {error&&<p role="alert">{error}</p>}</section>;
}
