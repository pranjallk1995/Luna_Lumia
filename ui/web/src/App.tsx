import { Clock, House, Keyboard, LogOut, Palette, RefreshCw, SlidersHorizontal, type LucideIcon } from "lucide-react";
import { useState } from "react";

import { lumia, useAct, useDashboard, type Settings } from "./api";
import { Brand, ForbiddenPage, SignInPage, UnreachablePage } from "./components/Gate";
import { DevicesTab } from "./components/DevicesTab";
import { HomeTab } from "./components/HomeTab";
import { PcTab } from "./components/PcTab";
import { SchedulesTab } from "./components/SchedulesTab";
import { SchemesLibrary } from "./components/SchemesLibrary";
import { useSession } from "./http";
import { messageOf, remember, remembered } from "./lib";

const SECTIONS = ["home", "schemes", "schedules", "pc", "devices"] as const;
type Section = (typeof SECTIONS)[number];

const NAV: { id: Section; label: string; icon: LucideIcon }[] = [
  { id: "home", label: "Home", icon: House },
  { id: "schemes", label: "Schemes", icon: Palette },
  { id: "schedules", label: "Schedules", icon: Clock },
  { id: "pc", label: "PC", icon: Keyboard },
  { id: "devices", label: "Devices", icon: SlidersHorizontal },
];

/** Checking the lights and signing out; switching every light is on Home's Now bar. */
function HeaderActions({ logoutUrl }: { logoutUrl: string }) {
  const act = useAct();
  const [checking, setChecking] = useState(false);

  const check = async () => {
    setChecking(true);
    // Light states are only read from the bulbs on demand (no background polling).
    await act(lumia.refreshLights, "The lights could not be checked.");
    setChecking(false);
  };

  return (
    <div className="lv-header-actions">
      <button className="lv-button" type="button" aria-label="Check lights" title="Check lights" disabled={checking} onClick={check}>
        <RefreshCw size={17} className={checking ? "ll-spin" : undefined} />
      </button>
      <a className="lv-button lv-sign-out" href={logoutUrl}>
        <LogOut size={16} />
        Sign out
      </a>
    </div>
  );
}

function Workspace({ logoutUrl, settings }: { logoutUrl: string; settings: Settings }) {
  const [section, setSection] = useState<Section>(() => remembered("ll-section", SECTIONS, "home"));
  const dashboard = useDashboard();
  // Rooms, groups, and lights chosen on Home; Schemes plays on the same ones.
  const [selection, setSelection] = useState<string[]>([]);
  const data = dashboard.data;

  const choose = (id: Section) => {
    setSection(id);
    remember("ll-section", id);
  };

  return (
    <main className="lv-page">
      <div className="lv-header-row">
        <Brand />
        <HeaderActions logoutUrl={logoutUrl} />
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
      {data && section === "home" && <HomeTab dashboard={data} settings={settings} selection={selection} onSelection={setSelection} />}
      {data && section === "pc" && <PcTab dashboard={data} settings={settings} />}
      {data && section === "schemes" && <SchemesLibrary dashboard={data} settings={settings} selection={selection} onSelection={setSelection} />}
      {data && section === "schedules" && <SchedulesTab dashboard={data} settings={settings} />}
      {data && section === "devices" && <DevicesTab dashboard={data} settings={settings} />}
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
