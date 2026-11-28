import type {CanyonSummary} from "../lib/ocrParser";

export function CanyonSummaryView({summary}:{summary:CanyonSummary}){
  return <section className="manual-review" aria-label="Canyon battle summary">
    <h4>Legion {summary.legion} · Place {summary.rank} of 3</h4>
    {summary.reported_at&&<p>Report: {summary.reported_at.replace("T"," ").replace("Z"," UTC")}</p>}
    <div className="table-wrap"><table><thead><tr><th>Place</th><th>Alliance</th><th>State / Legion</th><th>Points</th></tr></thead><tbody>{summary.teams.map(t=><tr key={t.rank}><td>{t.rank}{t.rank===summary.rank?" · Own":""}</td><td>[{t.tag}] {t.name}</td><td>#{t.state} · {t.legion}</td><td>{t.score.toLocaleString("en-US")}</td></tr>)}</tbody></table></div>
    {summary.stats.length>0&&<div className="table-wrap"><table><thead><tr><th>Statistic</th><th>Total</th><th>MVP</th></tr></thead><tbody>{summary.stats.map(s=><tr key={s.label}><td>{s.label}</td><td>{s.value}</td><td>{s.mvp? s.mvp+" · "+s.mvp_value:"—"}</td></tr>)}</tbody></table></div>}
  </section>;
}
