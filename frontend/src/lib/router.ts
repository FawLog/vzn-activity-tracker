import { useCallback, useEffect, useState } from "react";

export function navigate(target: string): void {
  if (`${window.location.pathname}${window.location.search}` === target) return;
  window.history.pushState({}, "", target);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export function useLocation(): { path: string; search: string } {
  const read = useCallback(
    () => ({ path: window.location.pathname, search: window.location.search }),
    [],
  );
  const [location, setLocation] = useState(read);
  useEffect(() => {
    const update = () => setLocation(read());
    window.addEventListener("popstate", update);
    return () => window.removeEventListener("popstate", update);
  }, [read]);
  return location;
}
