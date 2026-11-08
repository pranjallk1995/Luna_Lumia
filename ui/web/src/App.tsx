import { Clock, DoorOpen, Lightbulb, LogOut, Palette, Power, RefreshCw, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { lumia, useAct, useControl, useDashboard, type Dashboard, type Settings } from "./api";
import { Brand, ForbiddenPage, SignInPage, UnreachablePage } from "./components/Gate";
import { LightsTab } from "./components/LightsTab";
import { RoomsTab } from "./components/RoomsTab";
import { SchedulesTab } from "./components/SchedulesTab";
import { SchemesTab } from "./components/SchemesTab";
import { useSession } from "./http";
import { messageOf, remember, remembered } from "./lib";

const SECTIONS = ["lights", "rooms", "schemes", "schedules"] as const;
type Section = (typeof SECTIONS)[number];

const NAV: { id: Section; label: string; icon: LucideIcon }[] = [
  { id: "lights", label: "Lights", icon: Lightbulb },
  { id: "rooms", label: "Rooms", icon: DoorOpen },
  { id: "schemes", label: "Schemes", icon: Palette },
  { id: "schedules", label: "Schedules", icon: Clock },
];

function HeaderActions({ dashboard, logoutUrl }: { dashboard?: Dashboard; logoutUrl: string }) {
  const act = useAct();
  const control = useControl();
  const [checking, setChecking] = useState(false);
  // An offline light cannot be switched, so it does not hold "Turn all on" back.
  const live = dashboard?.lights.filter((light) => light.reachable !== false) ?? [];
  const allOn = live.length > 0 && live.every((light) => light.is_on);

  const check = async () => {
    setChecking(true);
    // Light states are only read from the bulbs on demand (no background polling).
    await act(lumia.refreshLights, "The lights could not be checked.");
    setChecking(false);
  };

  return (
    <div className="lv-header-actions">
      <button className="lv-button" type="button" aria-label="Check lights" disabled={checking} onClick={check}>
        <RefreshCw size={17} className={checking ? "ll-spin" : undefined} />
      </button>
      <button
        className="lv-button lv-button-primary lv-header-main"
        type="button"
        disabled={!dashboard}
        onClick={() => control({ type: "all", id: null }, { on: !allOn }, () => true, "Could not update all lights.")}
      >
        <Power size={17} />
        {allOn ? "Turn all off" : "Turn all on"}
      </button>
      <a className="lv-button lv-sign-out" href={logoutUrl}>
        <LogOut size={16} />
        Sign out
      </a>
    </div>
  );
}

function Workspace({ logoutUrl, settings }: { logoutUrl: string; settings: Settings }) {
  const [section, setSection] = useState<Section>(() => remembered("ll-section", SECTIONS, "lights"));
  const dashboard = useDashboard();
  const data = dashboard.data;

  const choose = (id: Section) => {
    setSection(id);
    remember("ll-section", id);
  };

  return (
    <main className="lv-page">
      <div className="lv-header-row">
        <Brand />
        <HeaderActions dashboard={data} logoutUrl={logoutUrl} />
      </div>

      <nav className="lv-nav" aria-label="Section">
        {NAV.map(({ id, label, icon: Icon }) => (
          <button
            className={section === id ? "lv-nav-item lv-nav-active" : "lv-nav-item"}
            type="button"
            key={id}
            aria-label={label}
            aria-current={section === id ? "page" : undefined}
            onClick={() => choose(id)}
          >
            <Icon size={17} />
            <span>{label}</span>
          </button>
        ))}
      </nav>

      {dashboard.error && !data && (
        <p className="lv-alert lv-alert-error">{messageOf(dashboard.error, "Luna Lumia's backend is unavailable.")}</p>
      )}
      {data && section === "lights" && <LightsTab dashboard={data} settings={settings} />}
      {data && section === "rooms" && <RoomsTab dashboard={data} settings={settings} />}
      {data && section === "schemes" && <SchemesTab dashboard={data} settings={settings} />}
      {data && section === "schedules" && <SchedulesTab dashboard={data} settings={settings} />}
      <footer className="lv-footer">Luna Lumia{settings.version && ` · v${settings.version}`}</footer>
    </main>
  );
}

export function App() {
  const { data: session, error, refetch } = useSession<Settings>();

  if (error) return <UnreachablePage onRetry={() => refetch()} />;
  if (!session) return null;
  if (session.status === "signed_out") return <SignInPage url={session.login_url} />;
  if (session.status === "forbidden") return <ForbiddenPage email={session.email} logoutUrl={session.logout_url} />;
  return <Workspace logoutUrl={session.logout_url} settings={session.settings} />;
}
