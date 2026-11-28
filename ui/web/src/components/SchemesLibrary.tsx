/** Schemes: the library, played on whatever Home has selected, with the weather and music automations beside it. */

import { CloudSun, Music, Pencil, Play, Plus, Search, Square, Trash2 } from "lucide-react";
import { useState } from "react";

import { lumia, useAct, type Automation, type Dashboard, type Scheme, type Settings } from "../api";
import { parseTargetKey, roomOf, schemeDetails, schemePayload, schemeSegments, selectedLights, targetKey } from "../dashboard";
import { Toggle } from "./controls";
import { Dialog } from "./Dialog";
import type { Selection } from "./HomeTab";
import { NewScheme, SchemeEditor, Transitions } from "./SchemesTab";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

type Filter = { id: string; label: string; test: (scheme: Scheme) => boolean };

const automated = (scheme: Scheme) => Boolean(scheme.weather_slots?.length || scheme.music_moods?.length);

const FILTERS: Filter[] = [
  { id: "all", label: "All", test: () => true },
  { id: "mine", label: "Yours", test: (scheme) => !scheme.is_preset },
  { id: "solid", label: "Solid", test: (scheme) => scheme.kind === "solid" && !automated(scheme) },
  { id: "sequence", label: "Sequence", test: (scheme) => scheme.kind === "sequence" && !scheme.effects?.length && !automated(scheme) },
  { id: "effects", label: "Effects", test: (scheme) => Boolean(scheme.effects?.length) },
  { id: "weather", label: "Weather", test: (scheme) => Boolean(scheme.weather_slots?.length) },
  { id: "music", label: "Music", test: (scheme) => Boolean(scheme.music_moods?.length) },
  { id: "keys", label: "Keys", test: (scheme) => scheme.kind === "keys" },
];

const words = (slot: string) => slot.replace(/_/g, " ").replace("/", ", ").replace(/^./, (first) => first.toUpperCase());

function Strip({ scheme, dashboard, className }: { scheme: Scheme; dashboard: Dashboard; className: string }) {
  return (
    <span className={className} aria-hidden="true">
      {schemeSegments(scheme, dashboard.transitions).map((segment, index) => (
        <i key={index} style={{ flexGrow: segment.weight, background: segment.color, opacity: segment.opacity }} />
      ))}
    </span>
  );
}

/** Where a scheme plays: its rooms, and lights in no room by name. */
function places(dashboard: Dashboard, lightIds: number[]) {
  const names = lightIds.map((id) => roomOf(dashboard, id)?.name ?? dashboard.lights.find((light) => light.id === id)?.name ?? "a light");
  return [...new Set(names)].join(", ");
}

function SchemeCard({ scheme, dashboard, onPlay, onEdit }: { scheme: Scheme; dashboard: Dashboard; onPlay: () => void; onEdit: () => void }) {
  const act = useAct();
  const toast = useToast();
  const playingOn = Object.entries(dashboard.playing)
    .filter(([, id]) => id === scheme.id)
    .map(([lightId]) => Number(lightId));
  const playing = playingOn.length > 0;
  const moving = scheme.effects?.length ? ` · ${scheme.effects.join(", ")}` : "";
  const kind = scheme.effects?.length ? "Effect · " : { solid: "Solid · ", sequence: "Sequence · ", keys: "Per key · " }[scheme.kind];

  const stop = () =>
    act(async () => {
      for (const id of playingOn) await lumia.stopSchemes({ type: "light", id });
    }, `Could not stop ${scheme.name}.`);
  const remove = async () => {
    const removed = await act(() => lumia.delete("scenes", scheme.id), `Could not delete ${scheme.name}.`);
    if (removed) toast(`${scheme.name} deleted`, { label: "Undo", run: () => act(() => lumia.create("scenes", schemePayload(scheme)), `Could not restore ${scheme.name}.`) });
  };

  return (
    <article className={playing ? "ll-scheme-card ll-scheme-card-on" : "ll-scheme-card"}>
      <Strip scheme={scheme} dashboard={dashboard} className="ll-card-strip" />
      <div className="ll-scheme-card-name">
        <strong className="ll-truncate" title={scheme.name}>
          {scheme.name}
        </strong>
        <span className="ll-now-label ll-truncate" title={`${kind}${schemeDetails(scheme)}${moving}`}>
          {scheme.is_preset ? "Built-in · " : ""}
          {kind}
          {schemeDetails(scheme)}
          {moving}
        </span>
      </div>
      <div className="ll-scheme-card-actions">
        {playing ? (
          <button className="lv-button ll-small-button ll-grow" type="button" onClick={stop}>
            <Square size={14} />
            Stop
          </button>
        ) : (
          <button className="lv-button ll-small-button ll-grow" type="button" onClick={onPlay}>
            <Play size={14} />
            Play
          </button>
        )}
        {!scheme.is_preset && (
          <>
            <button className="lv-icon-button" type="button" aria-label={`Edit ${scheme.name}`} title="Edit" onClick={onEdit}>
              <Pencil size={15} />
            </button>
            <button className="lv-icon-button" type="button" aria-label={`Delete ${scheme.name}`} title="Delete" onClick={remove}>
              <Trash2 size={15} />
            </button>
          </>
        )}
      </div>
      {playing && <span className="ll-playing-on">Playing on {places(dashboard, playingOn)}</span>}
    </article>
  );
}

/** Weather or music: the switch, and which scheme each slot or mood plays. */
function AutomationCard({ kind, dashboard }: { kind: "weather" | "music"; dashboard: Dashboard }) {
  const act = useAct();
  const setting: Automation | undefined = dashboard.automations?.[kind];
  const on = Boolean(setting?.enabled);
  const weather = kind === "weather";
  const slots = dashboard.scenes
    .flatMap((scheme) => (weather ? (scheme.weather_slots ?? []) : (scheme.music_moods ?? [])).map((slot) => ({ slot, scheme })))
    .sort((a, b) => a.slot.localeCompare(b.slot));
  const where =
    !setting || setting.target_type === "on"
      ? "Lights that are on"
      : setting.target_type === "all"
        ? "All lights"
        : ([...dashboard.rooms, ...dashboard.groups, ...dashboard.lights].find((item) => item.id === setting.target_id)?.name ?? "A deleted target");
  const toggle = (enabled: boolean) =>
    act(
      () => lumia.setAutomation(kind, { enabled, target_type: setting?.target_type ?? "on", target_id: setting?.target_id ?? null }),
      `Could not turn ${kind} automation ${enabled ? "on" : "off"}.`,
    );
  const Icon = weather ? CloudSun : Music;

  return (
    <section className={`ll-auto-card ll-auto-card-${kind}${on ? " ll-auto-card-on" : ""}`} aria-label={weather ? "Weather" : "Music"}>
      <div className="ll-auto-card-head">
        <Icon size={18} aria-hidden="true" />
        <span className="ll-now-text">
          <strong>{weather ? "Follow the weather" : "Follow the music"}</strong>
          <span className="ll-now-label">{weather ? `The sky outside · ${where}` : `What Luna Vibia plays · ${where}`}</span>
        </span>
        <Toggle label={weather ? "Follow the weather" : "Follow the music"} hideLabel checked={on} disabled={!setting} onChange={toggle} />
      </div>
      {slots.length ? (
        <ul className="ll-slots">
          {slots.map(({ slot, scheme }) => (
            <li key={`${slot}-${scheme.id}`}>
              <span className="ll-slot-when">{words(slot)}</span>
              <Strip scheme={scheme} dashboard={dashboard} className="ll-slot-strip" />
              <span className="ll-truncate">{scheme.name}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="lv-caption">No schemes are set for {weather ? "the weather" : "music moods"} yet.</p>
      )}
      <p className="lv-caption">Your assistant changes which scheme each {weather ? "kind of weather" : "mood"} plays.</p>
    </section>
  );
}

export function SchemesLibrary({ dashboard, settings, selection, onSelection }: TabProps & Selection) {
  const act = useAct();
  const toast = useToast();
  const [filter, setFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Scheme | null>(null);
  const [creating, setCreating] = useState(false);

  const chips = [
    ...dashboard.rooms.map((room) => ({ key: targetKey("group", room.id), name: room.name })),
    ...dashboard.groups.map((group) => ({ key: targetKey("group", group.id), name: `${group.name} group` })),
    ...dashboard.lights.filter((light) => selection.includes(targetKey("light", light.id))).map((light) => ({ key: targetKey("light", light.id), name: light.name })),
  ];
  const known = new Set(chips.map((chip) => chip.key));
  const current = selection.filter((key) => known.has(key));
  const toggle = (key: string) => onSelection(current.includes(key) ? current.filter((other) => other !== key) : [...current, key]);
  const targets = current.length ? current.map(parseTargetKey) : [{ type: "on", id: null }];
  const count = current.length ? selectedLights(dashboard, current).length : dashboard.lights.filter((light) => light.is_on && light.reachable !== false).length;

  const test = FILTERS.find((item) => item.id === filter)?.test ?? (() => true);
  const query = search.trim().toLowerCase();
  const shown = dashboard.scenes
    .filter((scheme) => test(scheme) && (!query || scheme.name.toLowerCase().includes(query)))
    .sort((a, b) => Number(a.is_preset) - Number(b.is_preset) || a.name.localeCompare(b.name));

  const play = (scheme: Scheme) =>
    act(async () => {
      let lights = 0;
      for (const target of targets) lights += (await lumia.applyScheme(scheme.id, target))?.light_ids?.length ?? 0;
      toast(`${scheme.name} on ${lights} light${lights === 1 ? "" : "s"}`);
    }, `Could not play ${scheme.name}.`);

  return (
    <>
      <section className="ll-plays-on" aria-label="Plays on">
        <span className="ll-now-label">Plays on</span>
        <button className={current.length ? "ll-choice" : "ll-choice ll-choice-active"} type="button" aria-pressed={!current.length} onClick={() => onSelection([])}>
          Every light that is on
        </button>
        {chips.map((chip) => (
          <button className={current.includes(chip.key) ? "ll-choice ll-choice-active" : "ll-choice"} type="button" aria-pressed={current.includes(chip.key)} key={chip.key} onClick={() => toggle(chip.key)}>
            {chip.name}
          </button>
        ))}
        <span className="ll-now-label ll-plays-note">
          {count} light{count === 1 ? "" : "s"} · the same selection as Home
        </span>
      </section>

      <div className="ll-split">
        <section className="ll-split-main" aria-labelledby="schemes-title">
          <div className="ll-section-head">
            <h2 id="schemes-title">
              Schemes <span className="ll-count">{dashboard.scenes.length}</span>
            </h2>
            <button className="lv-button lv-button-primary" type="button" onClick={() => setCreating(true)}>
              <Plus size={17} />
              New scheme
            </button>
          </div>
          <div className="ll-filters">
            <div className="ll-chips" role="group" aria-label="Show">
              {FILTERS.map((item) => {
                const total = dashboard.scenes.filter(item.test).length;
                return (
                  (total > 0 || item.id === "all") && (
                    <button className={filter === item.id ? "ll-choice ll-choice-active" : "ll-choice"} type="button" aria-pressed={filter === item.id} key={item.id} onClick={() => setFilter(item.id)}>
                      {item.label} <span className="ll-count">{total}</span>
                    </button>
                  )
                );
              })}
            </div>
            <label className="ll-search">
              <Search size={15} />
              <input className="lv-input" type="search" placeholder="Search schemes" aria-label="Search schemes" value={search} onChange={(event) => setSearch(event.target.value)} />
            </label>
          </div>
          {shown.length ? (
            <div className="ll-scheme-cards">
              {shown.map((scheme) => (
                <SchemeCard scheme={scheme} dashboard={dashboard} onPlay={() => play(scheme)} onEdit={() => setEditing(scheme)} key={scheme.id} />
              ))}
            </div>
          ) : (
            <p className="lv-alert">No schemes match.</p>
          )}
        </section>
        <aside className="ll-split-side" aria-label="Automations">
          <AutomationCard kind="weather" dashboard={dashboard} />
          <AutomationCard kind="music" dashboard={dashboard} />
        </aside>
      </div>

      <Transitions dashboard={dashboard} />

      {creating && <NewScheme dashboard={dashboard} settings={settings} onClose={() => setCreating(false)} />}
      {editing && (
        <Dialog title={`Edit ${editing.name}`} size="large" onClose={() => setEditing(null)}>
          <SchemeEditor scheme={editing} dashboard={dashboard} settings={settings} onDone={() => setEditing(null)} />
        </Dialog>
      )}
    </>
  );
}
