import type {CalendarReview,ReviewFlag} from "../lib/calendar";
export const reviewLabel:Record<ReviewFlag,string>={reviewed:"Reviewed",partial:"Partial / unverified",not_recorded:"Not recorded",not_applicable:"Not applicable"};
export function CalendarReviewPanel({review}:{review:CalendarReview}){
  const fields=[["Historical roster",review.roster],["Registration",review.registration],["Attendance",review.attendance],["Results",review.results]] as const;
  return <section className="calendar-stage-timeline" aria-label="Evidence review status">
    <h4>Evidence review · {review.scope==="session"?"Linked session":"Whole event"}</h4>
    <p>{review.session_count} recorded session{review.session_count===1?"":"s"} · {review.publication==="published"?"Published":"Draft"}</p>
    <div className="table-wrap"><table><tbody>{fields.map(([name,value])=><tr key={name}><th scope="row">{name}</th><td>{reviewLabel[value]}</td></tr>)}</tbody></table></div>
    {review.final_attendance_review!==null&&<p>Final attendance review (whole event): {review.final_attendance_review?"Published":"Not finalized"}</p>}
    <small>Saved evidence flags only. Published does not mean complete; missing evidence is not absence. Session review is not group-wide review.</small>
  </section>;
}
