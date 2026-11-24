import { EmptyState } from "../components/Feedback";
import { navigate } from "../lib/router";

export function NotFoundPage() {
  return <div className="page"><EmptyState title="Page not found" description="The requested operation surface does not exist." action={<button className="button button--primary" onClick={() => navigate("/")}>Return to overview</button>} /></div>;
}
