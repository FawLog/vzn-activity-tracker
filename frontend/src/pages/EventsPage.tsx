import { CalendarRange, FilePlus } from "lucide-react";
import { EventIcon } from "../components/EventIcon";
import { useEffect, useState } from "react";
import { EmptyState, ErrorState, LoadingState } from "../components/Feedback";
import { PageHeader } from "../components/Page";
import { api } from "../lib/api";
import { useGroupContext } from "../lib/group-context";
import { eventLabel, formatDate, eventTypeOptions } from "../lib/format";
import { navigate } from "../lib/router";
import type { EventRecord } from "../lib/types";

export function EventsPage() {
  const { selectedGroup, selectedAlliance } = useGroupContext();
  const groupId=selectedGroup?.id,allianceId=selectedAlliance?.id;
  const [sortValue,setSortValue]=useState("occurred_on:desc");
  const [status,setStatus]=useState("all");
  const [type,setType]=useState("all");
  const [query,setQuery]=useState("");
  const [retry,setRetry]=useState(0);
  const key=groupId+"|"+allianceId+"|"+sortValue+"|"+retry;
  const [loaded,setLoaded]=useState<{key:string;items:EventRecord[]}|null>(null);
  const [failure,setFailure]=useState<{key:string;message:string}|null>(null);
  useEffect(()=>{
    if(!groupId||!allianceId)return;
    let live=true;
    const [sort,direction]=sortValue.split(":");
    api.events(groupId,allianceId,sort,direction).then(r=>{if(live)setLoaded({key,items:r.items});}).catch(e=>{if(live)setFailure({key,message:e instanceof Error?e.message:"Unable to load history"});});
    return()=>{live=false};
  },[groupId,allianceId,sortValue,key]);
  if(!selectedGroup||!selectedAlliance)return <div className="page"><EmptyState title="No active alliance" description="Select an alliance before viewing event history."/></div>;
  const events=loaded?.key===key?loaded.items:null;
  const error=failure?.key===key?failure.message:"";
  const writable=selectedGroup.status==="active"&&selectedAlliance.status==="active";
  const visible=(events??[]).filter(r=>(status==="all"||r.status===status)&&(type==="all"||r.event_type===type)&&(!query.trim()||[eventLabel(r.event_type),r.occurred_on,r.id,r.alliance_name??""].join(" ").toLowerCase().includes(query.trim().toLowerCase())));
  return <div className="page"><PageHeader title="Event history" description={selectedAlliance.name+" · Actual records, historical imports and corrections"} action={<button className="button button--primary" onClick={()=>navigate("/calendar")}><CalendarRange size={17}/>Open calendar</button>}/>
    <section className="data-panel calendar-detail"><h2>Historical records</h2><p>Use Calendar to enter registration and results for scheduled events. Import here only when no suitable schedule exists. Existing drafts and published records remain available for review.</p>{writable&&<button className="button button--secondary" onClick={()=>navigate("/admin?mode=events")}><FilePlus size={16}/>Import historical event</button>}</section>
    <div className="toolbar calendar-toolbar"><label className="select-control">Find record<input aria-label="Find record" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Event, UTC date or ID"/></label><label className="select-control">Record status<select aria-label="Record status" value={status} onChange={e=>setStatus(e.target.value)}><option value="all">All statuses</option><option value="draft">Draft</option><option value="published">Published</option></select></label><label className="select-control">Event type<select aria-label="Event type" value={type} onChange={e=>setType(e.target.value)}><option value="all">All types</option>{eventTypeOptions.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></label><label className="select-control">Sort<select aria-label="Sort" value={sortValue} onChange={e=>setSortValue(e.target.value)}><option value="occurred_on:desc">Newest event date</option><option value="occurred_on:asc">Oldest event date</option><option value="event_type:asc">Event type</option><option value="status:asc">Status</option></select></label></div>
    {error?<ErrorState message={error} action={<button className="button button--quiet" onClick={()=>setRetry(n=>n+1)}>Retry</button>}/>:!events?<LoadingState label="Loading event history"/>:!visible.length?<EmptyState title={events.length?"No matching records":"No event records yet"} description={events.length?"Change the filters to find other records.":"Enter data through Calendar, or import a historical record if no schedule exists."} action={<button className="button button--secondary" onClick={()=>events.length?(setStatus("all"),setType("all"),setQuery("")):navigate("/calendar")}>{events.length?"Clear filters":"Open calendar"}</button>}/>:<section className="data-panel data-panel--page"><div className="section-header"><p>{visible.length} of {events.length} records</p></div><div className="table-wrap"><table><thead><tr><th>Event</th><th>Date</th><th>Status</th><th className="number-cell">Participants</th><th/></tr></thead><tbody>{visible.map(record=><tr key={record.id} className="clickable-row"><td><button className="table-link event-name" onClick={()=>navigate("/events/"+encodeURIComponent(record.id))}><EventIcon eventType={record.event_type}/><span>{eventLabel(record.event_type)}</span></button></td><td>{formatDate(record.occurred_on)}</td><td><span className={`status status--${record.status}`}>{record.status}</span></td><td className="number-cell">{record.participant_count??"—"}{record.registered_count!=null&&record.participant_count!=null?` / ${record.registered_count}`:""}<small className="table-subline">{record.registered_count!=null?"Attended / Registered":record.participant_label??""}{record.participant_complete===false&&record.participant_count!=null?" · Partial":""}</small></td><td className="row-arrow">→</td></tr>)}</tbody></table></div></section>}
  </div>;
}
