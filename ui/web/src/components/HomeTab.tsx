/** Home: what is on now, every room as a tile glowing in its lights' colors, and one panel that changes what you select. */

import { AlarmClock, ChevronDown, CloudSun, Music, Palette, Play, Power, Square, Sun, Thermometer, X } from "lucide-react";
import { useEffect, useState } from "react";

import { lumia, useAct, useControl, type Automation, type Dashboard, type Light, type LightState, type Settings, type Target } from "../api";
import {
  everydaySchemes,
  homeTiles,
  lightState,
  mostCommon,
  parseTargetKey,
  playingNow,
  playingScheme,
  schemeSegments,
  selectedLights,
  shownBrightness,
  shownColor,
  targetKey,
  temperatureSchemes,
  tileGlow,
  tileStatus,
  upcomingSchedule,
  type Tile,
} from "../dashboard";
import { remember, remembered } from "../lib";
import { Bulb, ColorChips, ColorInput, Slider, TemperatureChips, Toggle } from "./controls";

type TabProps = { dashboard: Dashboard; settings: Settings };

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** The current minute, so "Next" moves on without a reload. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 30_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function AutomationButton({ kind, setting }: { kind: "weather" | "music"; setting?: Automation }) {
  const act = useAct();
  const on = Boolean(setting?.enabled);
  const Icon = kind === "weather" ? CloudSun : Music;
  const label = kind === "weather" ? "Weather" : "Music";
  const toggle = () =>
    act(
      () => lumia.setAutomation(kind, { enabled: !on, target_type: setting?.target_type ?? "on", target_id: setting?.target_id ?? null }),
      `Could not turn ${label.toLowerCase()} automation ${on ? "off" : "on"}.`,
    );
  return (
    <button
      className={`ll-auto ll-auto-${kind}${on ? " ll-auto-on" : ""}`}
      type="button"
      aria-pressed={on}
      disabled={!setting}
      title={kind === "weather" ? "The lights take on the sky outside" : "The lights follow the mood of what Luna Vibia plays"}
      onClick={toggle}
    >
      <Icon size={15} />
      {label} · {on ? "on" : "off"}
    </button>
  );
}

/** The whole house at a glance: power, what is playing, the next schedule, and the automations. */
function NowBar({ dashboard }: { dashboard: Dashboard }) {
  const act = useAct();
  const control = useControl();
  const now = useNow();
  const { lights } = dashboard;
  const on = lights.filter((light) => lightState(light) === "on");
  const offline = lights.filter((light) => lightState(light) === "offline").length;
  const playing = playingNow(dashboard);
  const next = upcomingSchedule(dashboard, now);
  const first = playing[0];
  const anyOn = on.length > 0;

  return (
    <section className="ll-now" aria-label="Now">
      <div className="ll-now-cell">
        <button
          className={anyOn ? "ll-power ll-power-on" : "ll-power"}
          type="button"
          aria-label={anyOn ? "Turn every light off" : "Turn every light on"}
          title={anyOn ? "Turn every light off" : "Turn every light on"}
          disabled={!lights.length}
          onClick={() => control({ type: "all", id: null }, { on: !anyOn }, (light) => light.reachable !== false, "Could not update all lights.")}
        >
          <Power size={18} />
        </button>
        <span className="ll-now-text">
          <span className="ll-now-label">Whole house</span>
          <strong>
            {on.length} of {lights.length} on
          </strong>
          <span className="ll-now-label">{offline ? <span className="ll-bad">{offline} offline</span> : `${lights.length} online`}</span>
        </span>
      </div>

      <div className="ll-now-cell">
        {first ? (
          <span className="ll-now-swatch" aria-hidden="true">
            {first.scheme &&
              schemeSegments(first.scheme, dashboard.transitions).map((segment, index) => (
                <i key={index} style={{ flexGrow: segment.weight, background: segment.color, opacity: segment.opacity }} />
              ))}
          </span>
        ) : (
          <Play size={20} className="ll-now-icon" aria-hidden="true" />
        )}
        <span className="ll-now-text">
          <span className="ll-now-label">Playing</span>
          <strong>{first ? (first.scheme?.name ?? "A scheme") + (playing.length > 1 ? ` + ${playing.length - 1} more` : "") : "Nothing"}</strong>
          <span className="ll-now-label ll-truncate">
            {first ? `${first.places.join(", ")} · ${plural(first.lights, "light")}` : "Lights hold their colors"}
          </span>
        </span>
        {first && (
          <button className="lv-button ll-small-button" type="button" onClick={() => act(() => lumia.stopSchemes({ type: "all", id: null }), "Could not stop the schemes.")}>
            <Square size={14} />
            Stop
          </button>
        )}
      </div>

      <div className="ll-now-cell ll-now-next">
        <AlarmClock size={20} className="ll-now-icon" aria-hidden="true" />
        <span className="ll-now-text">
          <span className="ll-now-label">Next</span>
          <strong className="ll-truncate">{next ? next.schedule.name : "No schedule"}</strong>
          <span className="ll-now-label ll-truncate">
            {next ? `${next.where} · ${next.label}${next.later ? ` · ${next.later} more this week` : ""}` : "Add one on the Schedules tab"}
          </span>
        </span>
      </div>

      <div className="ll-now-cell ll-now-autos">
        <span className="ll-now-label">Automations</span>
        <span className="ll-chips">
          <AutomationButton kind="weather" setting={dashboard.automations?.weather} />
          <AutomationButton kind="music" setting={dashboard.automations?.music} />
        </span>
      </div>
    </section>
  );
}

function RoomTile({ tile, dashboard, selected, onSelect }: { tile: Tile; dashboard: Dashboard; selected: boolean; onSelect: () => void }) {
  const control = useControl();
  const live = tile.lights.filter((light) => light.reachable !== false);
  const lit = live.filter((light) => light.is_on);
  const glow = tileGlow(dashboard, tile.lights);
  const playing = playingScheme(dashboard, lit);
  const members = new Set(tile.lights.map((light) => light.id));
  const single = tile.target.type === "light";

  return (
    <div className={`ll-tile${glow ? " ll-tile-lit" : ""}${selected ? " ll-tile-selected" : ""}`} style={glow ? { backgroundImage: glow } : undefined}>
      <button className="ll-tile-select" type="button" aria-pressed={selected} onClick={onSelect}>
        <span className="ll-tile-name">
          <strong>{tile.name}</strong>
          <span>{tileStatus(dashboard, tile.lights)}</span>
        </span>
        <span className="ll-tile-foot">
          <span className="ll-tile-dots" aria-hidden="true">
            {tile.lights.map((light) => (
              <Bulb color={shownColor(dashboard, light)} state={lightState(light)} small key={light.id} />
            ))}
          </span>
          <span className="ll-truncate">{playing ? playing.name : single ? "" : tile.lights.map((light) => light.name).join(", ")}</span>
        </span>
      </button>
      <span className="ll-tile-switch">
        <Toggle
          label={`${tile.name} on`}
          hideLabel
          checked={lit.length > 0}
          disabled={!live.length}
          onChange={(on) => control(tile.target, { on }, (light) => members.has(light.id) && light.reachable !== false, `Could not update ${tile.name}.`)}
        />
      </span>
      {selected && <span className="ll-tile-check" aria-hidden="true" />}
    </div>
  );
}

/** Changes the selection, or every light that is on when nothing is selected. */
function ControlPanel({ dashboard, settings, selection, onSelect, onClear }: TabProps & { selection: string[]; onSelect: (keys: string[]) => void; onClear: () => void }) {
  const act = useAct();
  const control = useControl();
  const [mode, setMode] = useState<"temperature" | "color">(() => remembered("ll-home-mode", ["temperature", "color"] as const, "temperature"));
  const [allSchemes, setAllSchemes] = useState(false);
  const [open, setOpen] = useState(false);

  const chosen = selection.length > 0;
  const lights = chosen ? selectedLights(dashboard, selection) : dashboard.lights.filter((light) => lightState(light) === "on");
  const reachable = lights.filter((light) => light.reachable !== false);
  const lit = reachable.filter((light) => light.is_on);
  const ids = new Set(lights.map((light) => light.id));
  const targets: Target[] = chosen ? selection.map(parseTargetKey) : [{ type: "on", id: null }];
  const names = [...dashboard.rooms, ...dashboard.groups, ...dashboard.lights.map((light) => ({ ...light, kind: "light" }))];
  const title = chosen
    ? selection
        .map((key) => {
          const { type, id } = parseTargetKey(key);
          return names.find((item) => item.id === id && (type === "light") === (item.kind === "light"))?.name ?? "";
        })
        .join(", ")
    : "Every light that is on";
  const fallback = chosen ? `Could not update ${title}.` : "Could not update the lights that are on.";

  /** One change for every selected room, group, and light; offline lights are left alone. */
  const send = (state: LightState) =>
    Promise.all(targets.map((target) => control(target, state, (light) => ids.has(light.id) && light.reachable !== false && (chosen || light.is_on), fallback)));
  const power = (on: boolean) =>
    chosen ? send({ on }) : control({ type: "all", id: null }, { on }, (light) => light.reachable !== false, "Could not update all lights.");
  const apply = (schemeId: number) =>
    act(async () => {
      for (const target of targets) await lumia.applyScheme(schemeId, target);
    }, fallback);
  const stop = () =>
    act(async () => {
      for (const target of targets) await lumia.stopSchemes(target);
    }, fallback);

  const chooseMode = (next: "temperature" | "color") => {
    setMode(next);
    remember("ll-home-mode", next);
  };

  const playingHere = [...new Set(lights.map((light) => dashboard.playing[light.id]).filter((id): id is number => id !== undefined))];
  const schemes = everydaySchemes(dashboard.scenes, playingHere);
  const shown = allSchemes ? schemes : schemes.slice(0, 6);
  const temperatures = temperatureSchemes(dashboard.scenes, settings.temperature_presets);
  const none = !lit.length;
  const brightness = mostCommon(lit.map((light) => shownBrightness(dashboard, light)), 100);
  const kelvin = mostCommon(lit.map((light) => light.color_temp), settings.default_color_temp);
  const color = mostCommon(lit.filter((light) => !light.color_temp).map((light) => light.color), "#FFBE55");

  return (
    <aside className={`ll-dock${open ? " ll-dock-open" : ""}${chosen ? " ll-dock-chosen" : ""}`} aria-label="Controls">
      <div className="ll-dock-head">
        <button className="ll-dock-toggle" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
          <span className="ll-now-label">{chosen ? "Changing" : "Nothing selected: changing"}</span>
          <strong className="ll-dock-title" title={title}>
            {title}
          </strong>
          <span className="ll-now-label">
            {plural(lights.length, "light")}
            {lit.length !== lights.length && ` · ${lit.length} on`}
          </span>
          <ChevronDown size={18} className="ll-dock-chevron" aria-hidden="true" />
        </button>
        {chosen && (
          <button className="lv-icon-button" type="button" aria-label="Clear the selection" title="Clear the selection" onClick={onClear}>
            <X size={17} />
          </button>
        )}
      </div>

      <div className="ll-dock-quick">
        <div className="ll-dock-power">
          <button className="lv-button" type="button" disabled={!reachable.length && chosen} onClick={() => power(true)}>
            On
          </button>
          <button className="lv-button" type="button" disabled={!lit.length} onClick={() => power(false)}>
            Off
          </button>
        </div>
        <Slider label={`Brightness of ${title}`} icon={Sun} min={1} max={100} unit="%" value={brightness} disabled={none} onCommit={(value) => send({ brightness: value })} />
      </div>

      <div className="ll-dock-more">
        <div className="ll-segments ll-segments-wide" role="group" aria-label="Light mode">
          <button className={mode === "temperature" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={mode === "temperature"} onClick={() => chooseMode("temperature")}>
            <Thermometer size={15} />
            White
          </button>
          <button className={mode === "color" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={mode === "color"} onClick={() => chooseMode("color")}>
            <Palette size={15} />
            Color
          </button>
        </div>
        {mode === "temperature" ? (
          <div className="ll-dock-group">
            <Slider label={`Temperature of ${title}`} icon={Thermometer} min={settings.min_color_temp} max={settings.max_color_temp} step={100} unit="K" value={kelvin} disabled={none} onCommit={(value) => send({ color_temp: value })} />
            <TemperatureChips schemes={temperatures} disabled={none} onPick={(scheme) => apply(scheme.id)} />
          </div>
        ) : (
          <div className="ll-dock-group ll-color-row">
            <ColorInput label={`Color of ${title}`} value={color} disabled={none} onCommit={(value) => send({ color: value })} />
            <ColorChips settings={settings} disabled={none} onPick={(value) => send({ color: value })} />
          </div>
        )}

        <div className="ll-dock-group">
          <div className="ll-dock-subhead">
            <span>Schemes</span>
            {playingHere.length > 0 && (
              <button className="ll-link-button" type="button" onClick={stop}>
                Stop
              </button>
            )}
          </div>
          <div className="ll-scheme-picks">
            {shown.map((scheme) => (
              <button
                className={playingHere.includes(scheme.id) ? "ll-scheme-pick ll-scheme-pick-on" : "ll-scheme-pick"}
                type="button"
                key={scheme.id}
                aria-pressed={playingHere.includes(scheme.id)}
                disabled={!reachable.length}
                onClick={() => apply(scheme.id)}
              >
                <span className="ll-pick-strip" aria-hidden="true">
                  {schemeSegments(scheme, dashboard.transitions).map((segment, index) => (
                    <i key={index} style={{ flexGrow: segment.weight, background: segment.color, opacity: segment.opacity }} />
                  ))}
                </span>
                <span className="ll-truncate">{scheme.name}</span>
              </button>
            ))}
          </div>
          {schemes.length > 6 && (
            <button className="ll-link-button" type="button" aria-expanded={allSchemes} onClick={() => setAllSchemes(!allSchemes)}>
              {allSchemes ? "Fewer" : `All ${schemes.length}`}
            </button>
          )}
        </div>

        {lights.length > 0 && (
          <div className="ll-dock-group">
            <div className="ll-dock-subhead">
              <span>Lights</span>
              <span className="ll-now-label">Select one to change it alone</span>
            </div>
            <ul className="ll-dock-lights">
              {lights.map((light: Light) => {
                const state = lightState(light);
                const key = targetKey("light", light.id);
                return (
                  <li key={light.id}>
                    <button className="ll-dock-light" type="button" aria-pressed={selection.length === 1 && selection[0] === key} onClick={() => onSelect([key])}>
                      <Bulb color={shownColor(dashboard, light)} state={state} small />
                      <span className="ll-truncate">{light.name}</span>
                      <span className="ll-now-label">{state === "on" ? `${shownBrightness(dashboard, light)}%` : state}</span>
                    </button>
                    <Toggle
                      label={`${light.name} on`}
                      hideLabel
                      checked={state === "on"}
                      disabled={state === "offline"}
                      onChange={(on) => control({ type: "light", id: light.id }, { on }, (other) => other.id === light.id, `Could not update ${light.name}.`)}
                    />
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </aside>
  );
}

/** Home's selection is kept by the page, so Schemes plays on the same rooms. */
export type Selection = { selection: string[]; onSelection: (keys: string[]) => void };

export function HomeTab({ dashboard, settings, selection, onSelection: setSelection }: TabProps & Selection) {
  const tiles = homeTiles(dashboard);
  const rooms = tiles.filter((tile) => tile.target.type === "group");
  const others = tiles.filter((tile) => tile.target.type === "light");

  // A room, group, or light deleted elsewhere drops out of the selection.
  const known = new Set([
    ...dashboard.rooms.map((room) => targetKey("group", room.id)),
    ...dashboard.groups.map((group) => targetKey("group", group.id)),
    ...dashboard.lights.map((light) => targetKey("light", light.id)),
  ]);
  const current = selection.filter((key) => known.has(key));
  const toggle = (key: string) => setSelection(current.includes(key) ? current.filter((other) => other !== key) : [...current, key]);

  if (!dashboard.lights.length) {
    return <p className="lv-alert">No lights yet. Add them on the Devices tab, which scans your network for them.</p>;
  }

  return (
    <>
      <NowBar dashboard={dashboard} />
      <div className="ll-home">
        <div className="ll-home-main">
          <div className="ll-section-head">
            <h2>
              Rooms <span className="ll-count">{dashboard.rooms.length}</span>
            </h2>
            <span className="lv-caption ll-inline">Select rooms to change them together</span>
          </div>
          <div className="ll-tiles">
            {rooms.map((tile) => (
              <RoomTile tile={tile} dashboard={dashboard} selected={current.includes(tile.key)} onSelect={() => toggle(tile.key)} key={tile.key} />
            ))}
          </div>
          {others.length > 0 && (
            <>
              <div className="ll-section-head ll-home-others">
                <h2>
                  Other lights <span className="ll-count">{others.length}</span>
                </h2>
                <span className="lv-caption ll-inline">In no room</span>
              </div>
              <div className="ll-tiles ll-tiles-small">
                {others.map((tile) => (
                  <RoomTile tile={tile} dashboard={dashboard} selected={current.includes(tile.key)} onSelect={() => toggle(tile.key)} key={tile.key} />
                ))}
              </div>
            </>
          )}
          {dashboard.groups.length > 0 && (
            <div className="ll-home-groups">
              <h2>Groups</h2>
              {dashboard.groups.map((group) => {
                const key = targetKey("group", group.id);
                const active = current.length === 1 && current[0] === key;
                return (
                  <button className={active ? "ll-choice ll-choice-active ll-group-pick" : "ll-choice ll-group-pick"} type="button" aria-pressed={active} key={group.id} onClick={() => setSelection(active ? [] : [key])}>
                    {group.name} <span className="ll-count">{group.light_ids.length}</span>
                  </button>
                );
              })}
            </div>
          )}
        </div>
        <ControlPanel dashboard={dashboard} settings={settings} selection={current} onSelect={setSelection} onClear={() => setSelection([])} />
      </div>
    </>
  );
}
