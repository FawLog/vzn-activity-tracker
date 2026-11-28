import { useLayoutEffect, useRef } from "react";

type Guard = { dirty: boolean; busy: boolean };
const guards = new Map<object, Guard>();
export function allowNavigation(): boolean {
  const values = [...guards.values()];
  if (values.some(v => v.busy)) {
    window.alert("An event operation is in progress. Wait for it to finish.");
    return false;
  }
  return !values.some(v => v.dirty) || window.confirm("Discard unsaved event changes and leave?");
}
function beforeUnload(event: BeforeUnloadEvent) {
  if ([...guards.values()].some(v => v.dirty || v.busy)) {
    event.preventDefault();
    event.returnValue = "";
  }
}
export function useNavigationGuard(dirty: boolean, busy: boolean) {
  const token = useRef({});
  useLayoutEffect(() => {
    const key = token.current;
    guards.set(key, {dirty, busy});
    if (dirty || busy) window.addEventListener("beforeunload", beforeUnload);
    return () => {
      guards.delete(key);
      if (![...guards.values()].some(v => v.dirty || v.busy))
        window.removeEventListener("beforeunload", beforeUnload);
    };
  }, [dirty, busy]);
}
