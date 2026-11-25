import { Search } from "lucide-react";
import { useState } from "react";
import { api } from "../lib/api";
import type { AlliancePreview } from "../lib/types";
import { Notice } from "./Feedback";

interface AllianceConnectionProps {
  stateId: string;
  tag: string;
  onConfirmed: (token: string) => void;
  confirmed: boolean;
}

export function AllianceConnection({ stateId, tag, onConfirmed, confirmed }: AllianceConnectionProps) {
  const [preview, setPreview] = useState<AlliancePreview | null>(null);
  const [finding, setFinding] = useState(false);

  const find = async () => {
    setFinding(true);
    onConfirmed("");
    try {
      setPreview(await api.previewAlliance(stateId, tag));
    } catch (error) {
      setPreview({ status: "failed", message: error instanceof Error ? error.message : "Unable to find alliance." });
    } finally {
      setFinding(false);
    }
  };

  if (confirmed) return <Notice tone="success">WhiteoutStats alliance confirmed. It will be imported immediately after saving.</Notice>;
  return <div className="alliance-connection"><button className="button button--secondary" type="button" disabled={!stateId || !tag || finding} onClick={() => void find()}><Search size={15} />{finding ? "Finding…" : "Find alliance"}</button>{preview?.status === "success" && preview.alliance ? <div className="sync-panel"><strong>{preview.alliance.name ?? "Unnamed alliance"} · {preview.alliance.tag ?? "—"}</strong><small>State {preview.alliance.state_id ?? "—"} · Alliance ID {preview.alliance.aid}</small>{preview.alliance.flag_url ? <img className="alliance-flag" src={preview.alliance.flag_url} alt="" /> : null}<span>Leader: {preview.alliance.leader_name ?? "—"} · Members: {preview.alliance.member_count ?? "—"}</span><span>Power: {preview.alliance.power ?? "—"} · State rank: {preview.alliance.power_rank ? `#${preview.alliance.power_rank}` : "—"}</span><div className="alliance-inline-form__actions"><button className="button button--primary" type="button" onClick={() => onConfirmed(preview.confirmation_token ?? "")}>Confirm alliance</button><button className="button button--quiet" type="button" onClick={() => setPreview(null)}>Not my alliance</button></div></div> : null}{preview && preview.status !== "success" ? <Notice tone={preview.status === "not_configured" ? "success" : "error"}>{preview.message ?? "Alliance was not found."}</Notice> : null}</div>;
}
