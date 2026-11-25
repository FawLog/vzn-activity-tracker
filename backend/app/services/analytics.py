"""Read-only, evidence-aware analytics over published session records."""
from collections import defaultdict, Counter
from datetime import date
from ..database import connection

TYPES = ("alliance_championship", "alliance_mobilization", "bear_trap", "foundry", "canyon")
OUTCOMES = ("positive", "negative", "excused", "unknown")
METRICS = {"bear_trap": ("damage",), "alliance_mobilization": ("points", "missions_completed"), "foundry": ("personal_points",), "canyon": ("personal_points",)}


def counts(values):
    c = Counter(values)
    result = {k: c[k] for k in OUTCOMES}
    known = c["positive"] + c["negative"]
    result["known"] = known
    result["eligible_unknown"] = c["unknown"]
    result["rate"] = round(100 * c["positive"] / known, 2) if known else None
    return result


def registration(row, session):
    if row["eligibility"] == "no_duty" or row["registration"] == "excused":
        return "excused"
    if row["registration"] == "registered":
        return "positive"
    if row["registration"] == "not_registered" and row["eligibility"] == "confirmed" and session["roster_complete"] and session["registration_complete"]:
        return "negative"
    return "unknown"


def attendance(row, session):
    if row["eligibility"] == "no_duty" or row["attendance"] in ("excused", "no_duty"):
        return "excused"
    if row["attendance"] == "confirmed_present":
        return "positive"
    if row["attendance"] == "confirmed_absent" and row["eligibility"] == "confirmed" and session["roster_complete"] and session["attendance_complete"]:
        return "negative"
    return "unknown"


def bear_cycle(sessions):
    by_key = {s["session_key"]: s["attendance_outcome"] for s in sessions}
    values = [by_key.get(k, "unknown") for k in ("trap_1", "trap_2")]
    if "positive" in values:
        return "positive"
    if values == ["negative", "negative"]:
        return "negative"
    if values == ["excused", "excused"]:
        return "excused"
    return "unknown"


def metric_summary(values):
    return {"samples": len(values), "total": str(sum(values)) if values else None,
            "average": round(sum(values) / len(values), 2) if values else None,
            "maximum": max(values) if values else None}


def report(path, group_id, alliance_id, start: date, end: date, fid=None):
    if end < start or (end-start).days > 365:
        raise ValueError("Date range must be between 1 and 366 days")
    with connection(path) as db:
        db.execute("BEGIN")
        if not db.execute("SELECT 1 FROM alliance_groups WHERE id=?", (group_id,)).fetchone():
            raise LookupError("Group not found")
        if alliance_id and not db.execute("SELECT 1 FROM alliances WHERE id=? AND group_id=?", (alliance_id,group_id)).fetchone():
            raise LookupError("Alliance not found in selected group")
        if fid is not None and not db.execute("SELECT 1 FROM player_group_profiles WHERE group_id=? AND player_fid=?", (group_id,fid)).fetchone():
            raise LookupError("Player not found in selected group")
        events = [dict(r) for r in db.execute("""
            SELECT e.id,e.event_type,e.occurred_on,e.alliance_id,a.name AS alliance_name
            FROM events e JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=?) AND e.status='published'
              AND e.occurred_on BETWEEN ? AND ?
            ORDER BY e.occurred_on,e.id
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat()))]
        sessions = defaultdict(list)
        for r in db.execute("""
            SELECT s.* FROM event_sessions s JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=?) AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
            ORDER BY s.session_key
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat())):
            item=dict(r);item["rows"]={};sessions[r["event_id"]].append(item)
        session_by_id={s["id"]:s for v in sessions.values() for s in v}
        for r in db.execute("""
            SELECT r.* FROM event_session_roster r JOIN event_sessions s ON s.id=r.session_id
            JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            JOIN player_group_profiles p ON p.player_fid=r.player_fid AND p.group_id=a.group_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=?) AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
              AND (? IS NULL OR r.player_fid=?)
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat(),fid,fid)):
            row=dict(r);row["metrics"]={};session_by_id[r["session_id"]]["rows"][r["player_fid"]]=row
        for m in db.execute("""
            SELECT m.* FROM event_session_metrics m JOIN event_sessions s ON s.id=m.session_id
            JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=?) AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
              AND (? IS NULL OR m.player_fid=?)
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat(),fid,fid)):
            row=session_by_id[m["session_id"]]["rows"].get(m["player_fid"])
            if row is not None:
                row["metrics"][m["metric_key"]]=m["raw_value"]
        profiles={}
        for p in db.execute("""
            SELECT p.player_fid AS fid,p.status AS group_status,p.primary_alliance_id,
            (SELECT n.nickname FROM player_nickname_observations n WHERE n.group_id=p.group_id AND n.player_fid=p.player_fid
              ORDER BY n.observed_at DESC,n.id DESC LIMIT 1) AS nickname
            FROM player_group_profiles p WHERE p.group_id=? AND (? IS NULL OR p.player_fid=?)
        """,(group_id,fid,fid)):
            profiles[p["fid"]]=dict(p)
    # Every historical participant is retained, plus current alliance roster for context.
    observed={f for ss in sessions.values() for s in ss for f in s["rows"]}
    included={f for f,p in profiles.items() if f in observed or (fid is not None or (p["group_status"]=="active" and (alliance_id is None or p["primary_alliance_id"]==alliance_id)))}
    histories=defaultdict(list)
    event_reports=[]
    for event in events:
        kind=event["event_type"]
        ss=sessions[event["id"]]
        fids={f for s in ss for f in s["rows"]}
        entries=[]
        for f in sorted(fids):
            evidence=[]
            for s in ss:
                row=s["rows"].get(f)
                if row is None:
                    continue
                evidence.append({"session_id":s["id"],"session_key":s["session_key"],"started_at":s["started_at"],
                    "nickname":row["nickname"],"eligibility":row["eligibility"],"registration":row["registration"],
                    "attendance":row["attendance"],"role":row["role"],"registered_by":row["registered_by"],
                    "registration_outcome":registration(row,s),"attendance_outcome":attendance(row,s),"metrics":row["metrics"]})
            entry={"fid":f,"event_id":event["id"],"event_type":kind,"occurred_on":event["occurred_on"],"alliance_id":event["alliance_id"],"alliance_name":event["alliance_name"],"sessions":evidence}
            if kind=="bear_trap":
                entry["cycle_attendance"]=bear_cycle(evidence)
            entries.append(entry)
            histories[f].append(entry)
        event_reports.append({**event,"session_count":len(ss),"recorded_players":len(fids),
            "evidence":[{k:s[k] for k in ("session_key","roster_complete","registration_complete","attendance_complete","results_complete")} for s in ss],
            "metrics":aggregate(entries,kind)})
    players=[]
    for f in sorted(included,key=lambda f:((profiles[f]["nickname"] or f).casefold(),f)):
        history=histories[f]
        players.append({**profiles[f],"metrics":{k:aggregate([e for e in history if e["event_type"]==k],k) for k in TYPES},
                        **({"history":history} if fid is not None else {})})
    return {"group_id":group_id,"alliance_id":alliance_id,"start":start.isoformat(),"end":end.isoformat(),
            "published_events":len(events),"events":event_reports,"players":players,
            "coverage":{"events_with_sessions":sum(bool(sessions[e["id"]]) for e in events),"events_without_sessions":sum(not sessions[e["id"]] for e in events)},
            "semantics":{"rates":"known positive / (known positive + known negative); unknown and excused excluded","population":"recorded evidence only; no inferred historical eligibility","bear":"one event is one cycle","legacy":"no session evidence means no analytics","metric_total":"decimal string"}}


def aggregate(entries, kind):
    evidence=[s for e in entries for s in e["sessions"]]
    out={"observed_events":len(entries),"observed_sessions":len(evidence)}
    if kind in ("alliance_championship","foundry","canyon"):
        out["registration"]=counts(s["registration_outcome"] for s in evidence)
    if kind=="bear_trap":
        out["attendance"]=counts(e["cycle_attendance"] for e in entries)
    if kind in ("foundry","canyon"):
        out["attendance"]=counts(s["attendance_outcome"] for s in evidence)
        out["reliability"]=counts(s["attendance_outcome"] for s in evidence if s["registration_outcome"]=="positive")
        out["no_shows"]=out["reliability"]["negative"]
    for metric in METRICS.get(kind,()):
        out[metric]=metric_summary([s["metrics"][metric] for s in evidence if metric in s["metrics"]])
    return out
