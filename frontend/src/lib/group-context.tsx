import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { api } from "./api";
import { useAuth } from "./auth";
import type { Alliance, AllianceGroup } from "./types";

interface GroupContextValue {
  groups: AllianceGroup[];
  alliances: Alliance[];
  selectedGroup: AllianceGroup | null;
  selectedAlliance: Alliance | null;
  loading: boolean;
  refresh: () => Promise<void>;
  selectGroup: (groupId: string) => void;
  selectAlliance: (allianceId: string) => void;
}

const GroupContext = createContext<GroupContextValue | null>(null);
const GROUP_KEY = "vzn-active-group";
const ALLIANCE_KEY = "vzn-active-alliance";

export function GroupProvider({ children }: { children: ReactNode }) {
  const { authenticated } = useAuth();
  const [groups, setGroups] = useState<AllianceGroup[]>([]);
  const [alliances, setAlliances] = useState<Alliance[]>([]);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(() => localStorage.getItem(GROUP_KEY));
  const [selectedAllianceId, setSelectedAllianceId] = useState<string | null>(() => localStorage.getItem(ALLIANCE_KEY));
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    if (!authenticated) { setGroups([]); setAlliances([]); return; }
    setLoading(true);
    try {
      const nextGroups = (await api.groups()).items;
      setGroups(nextGroups);
      const activeGroup = nextGroups.find((group) => group.id === selectedGroupId) ?? nextGroups.find((group) => group.status === "active") ?? nextGroups[0] ?? null;
      if (!activeGroup) { setAlliances([]); return; }
      if (activeGroup.id !== selectedGroupId) { setSelectedGroupId(activeGroup.id); localStorage.setItem(GROUP_KEY, activeGroup.id); }
      const nextAlliances = (await api.alliances(activeGroup.id)).items;
      setAlliances(nextAlliances);
      const activeAlliance = nextAlliances.find((alliance) => alliance.id === selectedAllianceId) ?? nextAlliances.find((alliance) => alliance.alliance_type === "primary") ?? nextAlliances[0] ?? null;
      if (activeAlliance && activeAlliance.id !== selectedAllianceId) { setSelectedAllianceId(activeAlliance.id); localStorage.setItem(ALLIANCE_KEY, activeAlliance.id); }
    } finally { setLoading(false); }
  }, [authenticated, selectedAllianceId, selectedGroupId]);

  useEffect(() => { void refresh(); }, [refresh]);

  const selectGroup = useCallback((groupId: string) => { setSelectedGroupId(groupId); localStorage.setItem(GROUP_KEY, groupId); setSelectedAllianceId(null); localStorage.removeItem(ALLIANCE_KEY); }, []);
  const selectAlliance = useCallback((allianceId: string) => { setSelectedAllianceId(allianceId); localStorage.setItem(ALLIANCE_KEY, allianceId); }, []);
  const selectedGroup = groups.find((group) => group.id === selectedGroupId) ?? null;
  const selectedAlliance = alliances.find((alliance) => alliance.id === selectedAllianceId) ?? null;
  const value = useMemo(() => ({ groups, alliances, selectedGroup, selectedAlliance, loading, refresh, selectGroup, selectAlliance }), [groups, alliances, selectedGroup, selectedAlliance, loading, refresh, selectGroup, selectAlliance]);
  return <GroupContext.Provider value={value}>{children}</GroupContext.Provider>;
}

export function useGroupContext(): GroupContextValue {
  const context = useContext(GroupContext);
  if (!context) throw new Error("useGroupContext must be used inside GroupProvider");
  return context;
}
