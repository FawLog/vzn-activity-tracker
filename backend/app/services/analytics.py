"""Read-only, evidence-aware analytics over published session records."""
from collections import defaultdict, Counter
from datetime import date
from ..database import connection
from .whiteoutstats import normalize_avatar_url

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


def bear_cycle(sessions, expected_keys=None, complete=False):
    by_key = {s["session_key"]: s["attendance_outcome"] for s in sessions}
    values = [by_key.get(k, "unknown") for k in (expected_keys or ("trap_1", "trap_2"))]
    if "positive" in values:
        return "positive"
    if complete and values and all(v in ("negative","excused") for v in values) and "negative" in values:
        return "negative"
    if complete and values and all(v == "excused" for v in values):
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
            SELECT e.id,e.event_type,e.occurred_on,e.alliance_id,e.bear_cycle_complete,a.name AS alliance_name
            FROM events e JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=? OR e.event_type=\'bear_trap\') AND e.status='published'
              AND e.occurred_on BETWEEN ? AND ?
            ORDER BY e.occurred_on,e.id
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat()))]
        sessions = defaultdict(list)
        for r in db.execute("""
            SELECT s.* FROM event_sessions s JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=? OR e.event_type=\'bear_trap\') AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
            ORDER BY s.session_key
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat())):
            item=dict(r);item["rows"]={};sessions[r["event_id"]].append(item)
        session_by_id={s["id"]:s for v in sessions.values() for s in v}
        for detail in db.execute("""SELECT f.* FROM foundry_session_details f JOIN event_sessions s ON s.id=f.session_id
            JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=?) AND e.event_type='foundry' AND e.status='published' AND e.occurred_on BETWEEN ? AND ?""",
            (group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat())):
            if detail["session_id"] in session_by_id:
                session_by_id[detail["session_id"]]["foundry_details"] = {k: detail[k] for k in ("outcome","own_score","opponent_score","opponent_tag","opponent_name","opponent_state")}
        for r in db.execute("""
            SELECT r.* FROM event_session_roster r JOIN event_sessions s ON s.id=r.session_id
            JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            JOIN player_group_profiles p ON p.player_fid=r.player_fid AND p.group_id=a.group_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=? OR e.event_type=\'bear_trap\') AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
              AND (? IS NULL OR r.player_fid=?)
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat(),fid,fid)):
            row=dict(r);row["metrics"]={};session_by_id[r["session_id"]]["rows"][r["player_fid"]]=row
        for m in db.execute("""
            SELECT m.* FROM event_session_metrics m JOIN event_sessions s ON s.id=m.session_id
            JOIN events e ON e.id=s.event_id JOIN alliances a ON a.id=e.alliance_id
            WHERE a.group_id=? AND (? IS NULL OR a.id=? OR e.event_type=\'bear_trap\') AND e.status='published' AND e.occurred_on BETWEEN ? AND ?
              AND (? IS NULL OR m.player_fid=?)
        """,(group_id,alliance_id,alliance_id,start.isoformat(),end.isoformat(),fid,fid)):
            row=session_by_id[m["session_id"]]["rows"].get(m["player_fid"])
            if row is not None:
                row["metrics"][m["metric_key"]]=m["raw_value"]
        profiles={}
        for p in db.execute("""
            SELECT p.player_fid AS fid,p.status AS group_status,p.primary_alliance_id,wsp.avatar_url,
            (SELECT n.nickname FROM player_nickname_observations n WHERE n.group_id=p.group_id AND n.player_fid=p.player_fid
              ORDER BY n.observed_at DESC,n.id DESC LIMIT 1) AS nickname
            FROM player_group_profiles p LEFT JOIN player_whiteoutstats_profiles wsp ON wsp.player_fid=p.player_fid AND wsp.group_id=p.group_id WHERE p.group_id=? AND (? IS NULL OR p.player_fid=?)
        """,(group_id,fid,fid)):
            profiles[p["fid"]]={**dict(p),"avatar_url":normalize_avatar_url(p["avatar_url"])}
        finalized_ids={r["event_id"] for r in db.execute("SELECT event_id FROM event_completion_reviews")}
        completed=defaultdict(dict)
        for r in db.execute("""SELECT r.* FROM event_completion_roster r JOIN events e ON e.id=r.event_id JOIN alliances a ON a.id=e.alliance_id WHERE a.group_id=? AND e.status='published' AND e.occurred_on BETWEEN ? AND ? AND (? IS NULL OR r.player_fid=?)""",(group_id,start.isoformat(),end.isoformat(),fid,fid)):
            completed[r["event_id"]][r["player_fid"]]=dict(r)
        home_history=defaultdict(list)
        for h in db.execute("SELECT player_fid,alliance_id,effective_observed_at,ended_observed_at FROM player_primary_alliance_history WHERE group_id=? AND (? IS NULL OR player_fid=?)",(group_id,fid,fid)):
            home_history[h["player_fid"]].append(dict(h))
    # Every historical participant is retained, plus current alliance roster for context.
    observed=set()
    included={f for f,p in profiles.items() if fid is not None or (p["group_status"]=="active" and (alliance_id is None or p["primary_alliance_id"]==alliance_id))}
    histories=defaultdict(list)
    event_reports=[]
    for event in events:
        kind=event["event_type"]
        ss=sessions[event["id"]]
        fids={f for s in ss for f in s["rows"]} | set(completed[event["id"]])
        entries=[]
        finalized=event["id"] in finalized_ids
        unknown_home=0
        for f in sorted(fids):
            homes={h["alliance_id"] for h in home_history[f] if h["effective_observed_at"][:10] < event["occurred_on"] and (h["ended_observed_at"] is None or h["ended_observed_at"][:10] > event["occurred_on"])}
            home=next(iter(homes)) if len(homes)==1 else None
            final_row=completed[event["id"]].get(f)
            if final_row and final_row["home_alliance_id"]:
                home=final_row["home_alliance_id"]
            if kind=="bear_trap":
                if home is None: unknown_home+=1
                if alliance_id is not None and home!=alliance_id: continue
            included.add(f)
            evidence=[]
            for s in ss:
                row=s["rows"].get(f)
                if row is None:
                    continue
                evidence.append({"session_id":s["id"],"session_key":s["session_key"],"started_at":s["started_at"],"host_alliance_id":s["host_alliance_id"],
                    "nickname":row["nickname"],"eligibility":row["eligibility"],"registration":row["registration"],
                    "attendance":row["attendance"],"role":row["role"],"registered_by":row["registered_by"],
                    "registration_outcome":registration(row,s),"attendance_outcome":attendance(row,s),"metrics":row["metrics"]})
            entry={"fid":f,"event_id":event["id"],"event_type":kind,"occurred_on":event["occurred_on"],"alliance_id":event["alliance_id"],"alliance_name":event["alliance_name"],"home_alliance_id":home,"sessions":evidence}
            final=final_row["outcome"] if final_row else None
            if kind == "foundry":
                # Explicit scores are the evidence; missing scores never become zero.
                for item in evidence:
                    score = item["metrics"].get("personal_points")
                    if final in ("excused", "no_duty") or item["eligibility"] == "no_duty" or item["attendance"] in ("excused", "no_duty"):
                        item["attendance_outcome"] = "excused"
                    elif score is not None:
                        item["attendance_outcome"] = "positive" if score > 0 else "negative" if item["registration_outcome"] == "positive" else "unknown"
                    elif item["attendance_outcome"] != "negative":
                        item["attendance_outcome"] = "unknown"
                registered = any(s["registration_outcome"] == "positive" for s in evidence)
                full_registration = len(ss) == 2 and all(s["registration_complete"] for s in ss)
                if final in ("excused", "no_duty"):
                    entry["cycle_registration"] = "excused"
                elif registered:
                    entry["cycle_registration"] = "positive"
                elif final_row and final_row["roster_member"] and full_registration:
                    entry["cycle_registration"] = "negative"
                else:
                    entry["cycle_registration"] = "unknown"
                if any(s["attendance_outcome"] == "positive" for s in evidence):
                    entry["cycle_attendance"] = "positive"
                elif final in ("excused", "no_duty"):
                    entry["cycle_attendance"] = "excused"
                elif final == "negative" and full_registration and all(s["results_complete"] for s in ss):
                    entry["cycle_attendance"] = "negative"
                else:
                    entry["cycle_attendance"] = "unknown"
                entry["attendance_finalized"] = final is not None
            elif final is not None:
                entry["attendance_finalized"]=True
                entry["cycle_attendance"]="excused" if final=="no_duty" else final
                if kind in ("foundry","canyon"):
                    for item in evidence:
                        if item["metrics"].get("personal_points",0)>0 or item["attendance"]=="confirmed_present":
                            item["attendance_outcome"]="positive"
                        elif item["registration_outcome"]=="positive" and item["attendance_outcome"]!="positive":
                            item["attendance_outcome"]="excused" if final in ("excused","no_duty") or item["attendance_outcome"]=="excused" else "negative"
            elif finalized:
                entry["cycle_attendance"]="unknown"
            elif kind=="bear_trap":
                entry["cycle_attendance"]=bear_cycle(evidence, [s["session_key"] for s in ss], bool(event["bear_cycle_complete"]))
            entries.append(entry)
            histories[f].append(entry)
        # Compare contribution within each actual event, not across unlike point units.
        contribution_points = {}
        if kind == "alliance_mobilization":
            for e in entries:
                values = [s["metrics"]["points"] for s in e["sessions"] if "points" in s["metrics"]]
                if values and not all(s["eligibility"] == "no_duty" for s in e["sessions"]):
                    contribution_points[e["fid"]] = str(sum(values))
        event_reports.append({**event,**({"foundry_battles":[{"session_key":s["session_key"],"started_at":s["started_at"],"alliance_id":event["alliance_id"],**s.get("foundry_details",{})} for s in ss]} if kind=="foundry" else {}),"contribution_points":contribution_points,
            "contribution_complete":bool(kind == "alliance_mobilization" and ss and all(s["results_complete"] and s["roster_complete"] for s in ss)),
            "session_count":len(ss),"recorded_players":len(entries),"unknown_home_players":unknown_home,
            "evidence":[{k:s[k] for k in ("session_key","host_alliance_id","roster_complete","registration_complete","attendance_complete","results_complete")} for s in ss],
            "metrics":aggregate(entries,kind), "activity_cells": {e["fid"]: activity_cell(e) for e in entries}})
    players=[]
    for f in sorted(included,key=lambda f:((profiles[f]["nickname"] or f).casefold(),f)):
        history=histories[f]
        players.append({**profiles[f],"metrics":{k:aggregate([e for e in history if e["event_type"]==k],k) for k in TYPES},
                        **({"history":history} if fid is not None else {})})
    return {"group_id":group_id,"alliance_id":alliance_id,"start":start.isoformat(),"end":end.isoformat(),
            "published_events":len(events),"events":event_reports,"players":players,
            "coverage":{"events_with_sessions":sum(bool(sessions[e["id"]]) for e in events),"events_without_sessions":sum(not sessions[e["id"]] for e in events)},
            "semantics":{"rates":"known positive / (known positive + known negative); unknown and excused excluded","population":"recorded evidence only; no inferred historical eligibility","bear":"one event is one cycle","legacy":"no session evidence means no analytics","metric_total":"decimal string"}}


def activity_cell(entry):
    kind=entry["event_type"]
    if kind == "foundry":
        outcome = entry.get("cycle_attendance", "unknown")
        if outcome == "negative":
            if entry.get("cycle_registration") == "negative":
                return "not_registered"
            if any(s["registration_outcome"] == "positive" and s["attendance_outcome"] == "negative" for s in entry["sessions"]):
                return "no_show"
        return outcome
    if "cycle_attendance" in entry:
        return entry["cycle_attendance"]
    if kind=="alliance_championship":
        values=[s["registration_outcome"] for s in entry["sessions"]]
    elif kind in ("foundry","canyon"):
        values=[s["attendance_outcome"] for s in entry["sessions"]]
    elif kind=="alliance_mobilization":
        return "recorded" if any("points" in s["metrics"] or "missions_completed" in s["metrics"] for s in entry["sessions"]) else "unknown"
    else:
        return "unknown"
    # Preserve conflicting session evidence rather than hiding a no-show behind presence.
    known=set(values)
    if len(known)==1:
        return values[0]
    return "mixed" if len(known-{"unknown"})>1 else "unknown"


def aggregate(entries, kind):
    evidence=[s for e in entries for s in e["sessions"]]
    out={"observed_events":len(entries),"observed_sessions":len(evidence)}
    if kind == "foundry":
        out["registration"]=counts(e.get("cycle_registration", "positive" if any(s["registration_outcome"] == "positive" for s in e["sessions"]) else "unknown") for e in entries)
        out["missed_unregistered"]=sum(activity_cell(e) == "not_registered" for e in entries)
        out["missed_registered"]=sum(activity_cell(e) == "no_show" for e in entries)
    elif kind in ("alliance_championship","canyon"):
        out["registration"]=counts(s["registration_outcome"] for s in evidence)
    if kind=="bear_trap":
        out["attendance"]=counts(e["cycle_attendance"] for e in entries)
    if kind in ("foundry","canyon"):
        out["attendance"]=counts(e.get("cycle_attendance", "positive" if any(s["attendance_outcome"]=="positive" for s in e["sessions"]) else "unknown") for e in entries)
        out["reliability"]=counts(s["attendance_outcome"] for s in evidence if s["registration_outcome"]=="positive")
        out["no_shows"]=out["reliability"]["negative"]
    for metric in METRICS.get(kind,()):
        out[metric]=metric_summary([s["metrics"][metric] for s in evidence if metric in s["metrics"]])
    return out
