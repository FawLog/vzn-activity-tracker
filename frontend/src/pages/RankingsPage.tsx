import { CalendarCheck2, Layers3, ShieldCheck } from "lucide-react";
import { PageHeader } from "../components/Page";
import { useGroupContext } from "../lib/group-context";

export function RankingsPage() {
  const { selectedGroup } = useGroupContext();
  const categories = [
    { icon: Layers3, title: "Contribution", copy: "Raw points remain separate for SvS Preparation, Mobilization, and Showdown." },
    { icon: CalendarCheck2, title: "Attendance", copy: "Regularity is based only on events with complete, verified coverage." },
    { icon: ShieldCheck, title: "Reliability", copy: "Registration commitments and confirmed attendance remain distinct." },
  ];
  return <div className="page"><PageHeader title="Rankings" description={selectedGroup ? `Three independent views for ${selectedGroup.name}. No universal usefulness score.` : "Select a group to view future rankings."} /><section className="ranking-intro"><strong>Not enough verified data</strong><p>Rankings remain unavailable until records have complete denominators and review history. No estimate is shown as fact.</p></section><div className="ranking-list">{categories.map(({ icon: Icon, title, copy }) => <article key={title}><Icon /><div><h2>{title}</h2><p>{copy}</p></div><span>Unavailable</span></article>)}</div></div>;
}
