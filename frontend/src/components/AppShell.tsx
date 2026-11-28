import {
  BarChart3,
  Activity,
  CalendarDays,
  CalendarRange,
  LogIn,
  LogOut,
  Menu,
  Search,
  Settings,
  Users,
  X,
  LayoutDashboard,
  Layers,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useAuth } from "../lib/auth";
import { useGroupContext } from "../lib/group-context";
import { navigate } from "../lib/router";
import { Brand } from "./Brand";
import { ProductionVersion } from "./ProductionVersion";

const navItems = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/players", label: "Players", icon: Users },
  { href: "/calendar", label: "Calendar", icon: CalendarRange },
  { href: "/events", label: "Events", icon: CalendarDays },
  { href: "/activity", label: "Activity", icon: Activity },
  { href: "/rankings", label: "Rankings", icon: BarChart3 },
  { href: "/groups", label: "Groups", icon: Layers },
  { href: "/admin", label: "Admin", icon: Settings },
];

export function AppShell({ path, children }: { path: string; children: ReactNode }) {
  const { authenticated, logout } = useAuth();
  const { groups, alliances, selectedGroup, selectedAlliance, selectGroup, selectAlliance } = useGroupContext();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement;
      if (event.key !== "/" || target.matches("input, textarea, select")) return;
      event.preventDefault();
      searchRef.current?.focus();
    };
    window.addEventListener("keydown", focusSearch);
    return () => window.removeEventListener("keydown", focusSearch);
  }, []);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    if (search.trim()) navigate(`/players?q=${encodeURIComponent(search.trim())}`);
  };

  const selectNav = (target: string) => {
    navigate(target);
    setMobileOpen(false);
  };

  const signOut = async () => {
    await logout();
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <aside className={`sidebar${mobileOpen ? " sidebar--open" : ""}`}>
        <div className="sidebar__mobile-head">
          <Brand />
          <button className="icon-button" onClick={() => setMobileOpen(false)} aria-label="Close navigation">
            <X size={20} />
          </button>
        </div>
        <div className="sidebar__brand"><Brand /></div>
        <div className="sidebar__rule" />
        <nav aria-label="Primary navigation">
          {navItems.map(({ href, label, icon: Icon }) => {
            const selected = href === "/" ? path === "/" : path.startsWith(href);
            return (
              <button
                key={href}
                className={`nav-item${selected ? " nav-item--selected" : ""}`}
                onClick={() => selectNav(href)}
              >
                <Icon size={19} strokeWidth={1.8} />
                <span>{label}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar__context">
          <span className="context-mark">WOS</span>
          <span><strong>Whiteout Survival</strong><small>Alliance workspace</small></span>
        </div>
      </aside>
      {mobileOpen && <button className="sidebar-scrim" aria-label="Close navigation" onClick={() => setMobileOpen(false)} />}

      <div className="workspace">
        <header className="topbar">
          <button className="icon-button topbar__menu" onClick={() => setMobileOpen(true)} aria-label="Open navigation">
            <Menu size={21} />
          </button>
          <div className="topbar__mobile-brand"><Brand compact /></div>
          {authenticated ? (
            <div className="topbar__workspace-tools">
              {selectedGroup ? <>
                <label className="context-select"><span>Group</span><select value={selectedGroup.id} onChange={(event) => selectGroup(event.target.value)} aria-label="Current group">{groups.map((group) => <option key={group.id} value={group.id}>{group.name}{group.status === "archived" ? " · archived" : ""}</option>)}</select></label>
                <label className="context-select"><span>Alliance</span><select value={selectedAlliance?.id ?? ""} onChange={(event) => selectAlliance(event.target.value)} aria-label="Current alliance">{alliances.map((alliance) => <option key={alliance.id} value={alliance.id}>{alliance.name} · {alliance.tag}</option>)}</select></label>
              </> : <span className="topbar__setup">Set up a group to begin</span>}
              <form className="global-search" onSubmit={submitSearch} role="search"><Search size={18} /><input ref={searchRef} value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search players by ID or nickname" aria-label="Search players" /><kbd>/</kbd></form>
            </div>
          ) : <div className="topbar__spacer" />}
          <div className="topbar__actions">
            <span className="system-state"><i />System operational</span>
            {authenticated ? (
              <button className="utility-button" onClick={signOut}><LogOut size={17} />Sign out</button>
            ) : (
              <button className="utility-button" onClick={() => navigate("/login")}><LogIn size={17} />Officer sign-in</button>
            )}
          </div>
        </header>
        <main className="main-content">{children}</main>
        <footer className="statusbar">
          <span><i />System operational</span>
          {authenticated && <ProductionVersion />}
          <span className="statusbar__note">Verified records only · no inferred absences</span>
        </footer>
      </div>
    </div>
  );
}
