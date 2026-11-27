import { CalendarDays } from "lucide-react";
import { useState } from "react";
import { eventIconUrl } from "../lib/eventIcons";

// Decorative: the adjacent event name supplies the accessible label.
export function EventIcon({ eventType }: { eventType: string }) {
  const url = eventIconUrl(eventType);
  const [failedUrl, setFailedUrl] = useState<string>();
  return <span className="event-icon" aria-hidden="true">
    {url && failedUrl !== url
      ? <img src={url} alt="" width={32} height={32} onError={() => setFailedUrl(url)} />
      : <CalendarDays size={20} />}
  </span>;
}
