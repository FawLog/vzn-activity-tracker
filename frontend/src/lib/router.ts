import { useEffect, useState } from "react";
import { allowNavigation } from "./navigation-guard";

const positionKey = "__vznNavigationPosition";
const read = () => ({ path: window.location.pathname, search: window.location.search });
let current = read();
let position = 0;
let initialized = false;
let restoring = false;
const subscribers = new Set<() => void>();
function notify() { current = read(); subscribers.forEach(fn => fn()); }
function initialize() {
  if (initialized) return;
  initialized = true;
  position = Number.isInteger(window.history.state?.[positionKey]) ? window.history.state[positionKey] : 0;
  window.history.replaceState({...window.history.state, [positionKey]:position}, "", window.location.href);
  current = read();
  window.addEventListener("popstate", () => {
    const next = window.history.state?.[positionKey];
    if (restoring) { restoring = false; notify(); return; }
    if (allowNavigation()) {
      position = Number.isInteger(next) ? next : position;
      notify();
    } else if (Number.isInteger(next) && next !== position) {
      restoring = true;
      window.history.go(position - next);
    } else {
      window.history.replaceState({...window.history.state,[positionKey]:position},"",current.path+current.search);
    }
  });
}
export function navigate(target: string): void {
  initialize();
  if (current.path+current.search === target || restoring || !allowNavigation()) return;
  window.history.pushState({[positionKey]:++position}, "", target);
  notify();
}
export function useLocation(): { path: string; search: string } {
  const [location, setLocation] = useState(read);
  useEffect(() => {
    initialize();
    const update = () => setLocation(current);
    subscribers.add(update);
    update();
    return () => { subscribers.delete(update); };
  }, []);
  return location;
}
