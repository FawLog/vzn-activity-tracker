import { ArrowLeft, FileCheck2 } from "lucide-react";
import { EventCalendarLinks } from "../components/CalendarEventLink";
import { EventIcon } from "../components/EventIcon";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate } from "../lib/format";
import { navigate } from "../lib/router";
import { ManualEventEditor, supportsManualEditor } from "../components/ManualEventEditor";
import type { EventRecord } from "../lib/types";

export function EventDetailPage({ id }: { id: string }) {
  const { selectedGroup } = useGroupContext();
  const [loaded, setLoaded] = useState<{key:string;record:EventRecord}|null>(null);
  const key=selectedGroup?.id+":"+id;
  const record=loaded?.key===key?loaded.record:null;
  const setRecord=(record:EventRecord)=>setLoaded({key,record});
  const [failure, setFailure] = useState<{key:string;message:string}|null>(null);
  const error=failure?.key===key?failure.message:"";
  const [managementError,setManagementError]=useState("");
  const [busy,setBusy]=useState(false);
  const [version,setVersion]=useState(0);
  useEffect(() => { let live=true; if (selectedGroup) api.event(selectedGroup.id,id).then(r=>{if(live)setLoaded({key,record:r});}).catch(e=>{if(live)setFailure({key,message:e.message});}); return()=>{live=false}; }, [id, selectedGroup,key]);
  if (!selectedGroup) return <div className="page"><LoadingState label="Selecting group" /></div>;
  if (error) return <div className="page"><ErrorState message={error} /></div>;
  if (!record) return <div className="page"><LoadingState label="Loading event record" /></div>;
  const manage=async(action:"delete"|"reopen"|"date")=>{
    const date=action==="date"?window.prompt("Event date (YYYY-MM-DD)",record.occurred_on):null;
    if(action==="date"&&(!date||date===record.occurred_on))return;
    if(!window.confirm(action==="delete"?"Permanently delete this event and all results?"+(record.status==="published"?" Published statistics will change.":""):action==="reopen"?"Reopen published event for corrections?":"Change event date?"))return;
    setBusy(true);setManagementError("");
    try{await api.manageEvent(selectedGroup.id,id,{action,confirmed:true,...(date?{occurred_on:date}:{})});if(action==="delete"){navigate("/events");return}setRecord(await api.event(selectedGroup.id,id));setVersion(v=>v+1)}catch(e){setManagementError(e instanceof Error?e.message:"Action failed")}finally{setBusy(false)}
  };
  return <div className="page"><button className="back-link back-link--page" onClick={() => navigate("/events")}><ArrowLeft size={18} />Event history</button><header className="event-header"><div><span className="event-header__type"><EventIcon eventType={record.event_type} />{eventLabel(record.event_type)}</span><h1>{formatDate(record.occurred_on)}</h1><p>{record.alliance_name ?? "Alliance"} · <span className={`status status--${record.status}`}>{record.status}</span></p></div><span className="event-header__id mono">ID {record.id.slice(0, 12)}</span></header><div className="manual-controls">{record.status==="draft"?<button className="button button--secondary" disabled={busy} onClick={()=>void manage("date")}>Edit date</button>:<button className="button button--secondary" disabled={busy} onClick={()=>void manage("reopen")}>Reopen event</button>}<button className="button button--quiet" disabled={busy} onClick={()=>void manage("delete")}>Delete event</button></div>{managementError&&<div role="alert" className="notice notice--error">{managementError}</div>}<p className="manual-help">For scheduled events, use the linked calendar workspace below. Historical corrections remain available here.</p><EventCalendarLinks key={selectedGroup.id+":"+record.id+":"+version} groupId={selectedGroup.id} eventId={record.id}/>{supportsManualEditor(record.event_type) && <ManualEventEditor key={selectedGroup.id + ":" + record.id+":"+version} groupId={selectedGroup.id} record={record} onPublished={() => setRecord({...record,status:"published"})} />}{(!supportsManualEditor(record.event_type) || !!record.participants?.length) && <section className="data-panel data-panel--page"><div className="section-header"><div><h2>Legacy results</h2><p>Participation and raw event-specific values will appear here after review.</p></div><FileCheck2 size={20} /></div>{record.participants?.length ? <div className="table-wrap"><table><thead><tr><th>FID</th><th>Player</th><th>Presence</th><th>Roster role</th><th>Raw points</th></tr></thead><tbody>{record.participants.map((participant) => <tr key={participant.fid}><td className="mono">{participant.fid}</td><td>{participant.nickname}</td><td>{participant.presence_status.replaceAll("_", " ")}</td><td>{participant.roster_role ?? "Unknown"}</td><td>{participant.raw_points ?? "—"}</td></tr>)}</tbody></table></div> : <EmptyState compact title="No reviewed results" description="No participant result records have been added to this event." />}</section>}</div>;
}
