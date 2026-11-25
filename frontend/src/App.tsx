import { useEffect, type ReactNode } from "react";
import { AppShell } from "./components/AppShell";
import { LoadingState } from "./components/Feedback";
import { useAuth } from "./lib/auth";
import { navigate, useLocation } from "./lib/router";
import { ActivityPage } from "./pages/ActivityPage";
import { AdminPage } from "./pages/AdminPage";
import { CreateGroupPage } from "./pages/CreateGroupPage";
import { EventDetailPage } from "./pages/EventDetailPage";
import { EventsPage } from "./pages/EventsPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { OverviewPage } from "./pages/OverviewPage";
import { GroupsPage } from "./pages/GroupsPage";
import { OnboardingPage } from "./pages/OnboardingPage";
import { PlayerProfilePage } from "./pages/PlayerProfilePage";
import { PlayersPage } from "./pages/PlayersPage";
import { RankingsPage } from "./pages/RankingsPage";

function Protected({ children }: { children: ReactNode }) {
  const { authenticated, loading } = useAuth();
  useEffect(() => { if (!loading && !authenticated) navigate("/login"); }, [authenticated, loading]);
  if (loading || !authenticated) return <div className="page"><LoadingState label="Verifying access" /></div>;
  return children;
}

export default function App() {
  const { path } = useLocation();
  const { loading } = useAuth();
  useEffect(() => {
    const click = (event: MouseEvent) => {
      const link = (event.target as Element).closest<HTMLAnchorElement>("a[data-nav]");
      if (!link || event.defaultPrevented || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault(); navigate(link.pathname);
    };
    document.addEventListener("click", click);
    return () => document.removeEventListener("click", click);
  }, []);
  if (loading) return <div className="boot-screen"><LoadingState label="Establishing secure session" /></div>;
  if (path === "/login") return <LoginPage />;
  let content: ReactNode;
  if (path === "/") content = <Protected><OverviewPage /></Protected>;
  else if (path === "/onboarding") content = <Protected><OnboardingPage /></Protected>;
  else if (path === "/groups/new") content = <Protected><CreateGroupPage /></Protected>;
  else if (path === "/groups") content = <Protected><GroupsPage /></Protected>;
  else if (path === "/players") content = <Protected><PlayersPage /></Protected>;
  else if (path.startsWith("/players/")) content = <Protected><PlayerProfilePage fid={decodeURIComponent(path.slice(9))} /></Protected>;
  else if (path === "/events") content = <Protected><EventsPage /></Protected>;
  else if (path.startsWith("/events/")) content = <Protected><EventDetailPage id={decodeURIComponent(path.slice(8))} /></Protected>;
  else if (path === "/activity") content = <Protected><ActivityPage /></Protected>;
  else if (path === "/rankings") content = <Protected><RankingsPage /></Protected>;
  else if (path === "/admin") content = <Protected><AdminPage /></Protected>;
  else content = <NotFoundPage />;
  return <AppShell path={path}>{content}</AppShell>;
}
