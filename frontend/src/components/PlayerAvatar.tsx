import { UserRound } from "lucide-react";
import { useState } from "react";

export function PlayerAvatar({ url, large = false }: { url?: string | null; large?: boolean }) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  let src: string | null = null;
  try {
    const parsed = new URL(url ?? "");
    if (parsed.protocol === "https:" && !parsed.username && !parsed.password) src = parsed.href;
  } catch { /* A missing or invalid provider URL uses the placeholder. */ }
  return <span className={large ? "roster-avatar profile-avatar" : "roster-avatar"} aria-hidden="true">{src && failedUrl !== src
    ? <img src={src} alt="" width={large ? 64 : 32} height={large ? 64 : 32} loading={large ? "eager" : "lazy"} decoding="async" referrerPolicy="no-referrer" onError={() => setFailedUrl(src)} />
    : <UserRound size={large ? 30 : 17} />}</span>;
}

