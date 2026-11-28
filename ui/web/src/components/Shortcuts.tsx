import { Pencil, Plus, Save, Trash2 } from "lucide-react";
import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";

import {
  lumia, shortcuts, useAct, useShortcutAct, useShortcuts, type Dashboard, type Effect, type Hotkey, type HotkeyPayload, type KeyGroup, type Light, type PcApp,
} from "../api";
import { targetKey, targetOptions } from "../dashboard";
import { animate, animatedScheme, comboOf, keyLabel, leftToRight, type Led, type Pattern } from "../pc";
import { EffectPicker, useTicker } from "./Effects";
import { ColorInput, Toggle } from "./controls";
import { useToast } from "./Toasts";

const PAINTED = "painted";
const ALL = "all";

/** What moves on a pattern in the PC editor, and the pattern as it looks right now. */
export function usePatternMotion(leds: Led[], pattern: Pattern, groups: Record<string, string[]>) {
  const [effect, setEffect] = useState<Effect | null>(null);
  const [moves, setMoves] = useState(PAINTED);
  const all = useMemo(() => leds.map((led) => led.key), [leds]);
  const names = moves === PAINTED ? Object.keys(pattern.keys) : moves === ALL ? all : groups[moves] ?? [];
  const keys = leftToRight(names, leds);
  const effects: Effect[] = effect && keys.length ? [{ ...effect, keys }] : [];
  const t = useTicker(effects.length > 0);
  const shown = useMemo(() => animate(pattern, effects, t, all), [pattern, effects, t, all]);
  /** Open a saved scheme's first effect: on its own keys when they are not the painted ones. */
  const load = (saved: Effect[]) => {
    const [first] = saved;
    setEffect(first ? { ...first, keys: null } : null);
    setMoves(first?.keys?.length === all.length ? ALL : PAINTED);
  };
  return { effect, setEffect, moves, setMoves, effects, shown, load, keys };
}

export type Motion = ReturnType<typeof usePatternMotion>;

/** The Brush panel's Effect: what moves, how, and on which keys. */
export function MotionControls({ pattern, groups, motion, keyboard }: { pattern: Pattern; groups: Record<string, string[]>; motion: Motion; keyboard: boolean }) {
  const painted = Object.keys(pattern.keys).length;
  const base = Object.values(pattern.keys)[0] ?? pattern.background;
  const where = motion.moves === PAINTED ? "on the painted keys" : motion.moves === ALL ? `on every ${keyboard ? "key" : "LED"}` : `on ${motion.moves}`;
  return (
    <div className="ll-pc-section">
      <EffectPicker effect={motion.effect} onChange={motion.setEffect} base={base} keyed label="Effect"
        note={motion.effect ? (motion.effect.type === "rainbow" ? `every hue, ${where}` : where) : "still colors"} />
      {motion.effect && (
        <label className="ll-pc-field ll-pc-wide">
          Moves
          <select className="lv-select" value={motion.moves} onChange={(event) => motion.setMoves(event.target.value)}>
            <option value={PAINTED}>Painted {keyboard ? "keys" : "LEDs"} ({painted})</option>
            <option value={ALL}>Every {keyboard ? "key" : "LED"}</option>
            {Object.keys(groups).map((group) => <option value={group} key={group}>{group}</option>)}
          </select>
        </label>
      )}
      {motion.effect && !motion.keys.length && <p className="lv-caption">Paint some keys first, or pick other keys to move.</p>}
    </div>
  );
}

/** Save the pattern, and what moves on it, as a per-key scheme. */
export function SaveScene({ light, pattern, motion }: { light: Light; pattern: Pattern; motion: Motion }) {
  const act = useAct();
  const toast = useToast();
  const [name, setName] = useState("");
  const save = async (event: FormEvent) => {
    event.preventDefault();
    const named = name.trim();
    if (!named) return;
    if (await act(() => lumia.create("scenes", animatedScheme(named, pattern, motion.effects)), `Could not save ${named}.`)) {
      toast(`Saved ${named}: play it here, or from Schemes, rooms, schedules and hotkeys`);
      setName("");
    }
  };
  return (
    <form className="ll-pc-section" onSubmit={save}>
      <label className="lv-field">
        Save as a scheme
        <input className="lv-input" value={name} maxLength={100} onChange={(event) => setName(event.target.value)}
          placeholder={motion.effects.length ? `${light.name} ${motion.effects[0].type}` : "Gaming red"} />
      </label>
      <button className="lv-button ll-lit-button" type="submit" disabled={!name.trim()}>
        <Save size={16} /> Save scheme
      </button>
      <span className="lv-caption">Saved patterns and their effect show under Per-key schemes here and in Schemes, ready for a schedule or a hotkey.</span>
    </form>
  );
}

/** Press keys to record a combination; shown as it will be saved. */
function ComboInput({ value, onChange }: { value: string; onChange: (combo: string) => void }) {
  const [held, setHeld] = useState("");
  const keyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Tab" && !event.ctrlKey && !event.altKey && !event.metaKey) return;
    event.preventDefault();
    if (event.key === "Backspace" && !event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey) return onChange("");
    const combo = comboOf(event.nativeEvent);
    if (combo) {
      onChange(combo);
      setHeld("");
    } else {
      setHeld([event.ctrlKey && "Ctrl", event.altKey && "Alt", event.shiftKey && "Shift", event.metaKey && "Win"].filter(Boolean).join("+") + "+…");
    }
  };
  return (
    <input className="lv-input ll-combo" value={held || value} placeholder="Press the keys, e.g. Ctrl+Alt+1" aria-label="Key combination"
      onKeyDown={keyDown} onKeyUp={() => setHeld("")} onBlur={() => setHeld("")} onChange={(event) => onChange(event.target.value)} />
  );
}

const Keycaps = ({ keys }: { keys: string[] }) => (
  <span className="ll-keycaps">{keys.map((key) => <kbd key={key}>{keyLabel(key) || key}</kbd>)}</span>
);

const ACTIONS = { open: "Open an app", scene: "Play a scheme", stop: "Stop what plays", off: "Turn off" } as const;

function HotkeyForm({ dashboard, apps, editing, onDone }: { dashboard: Dashboard; apps: PcApp[]; editing?: Hotkey; onDone: () => void }) {
  const act = useShortcutAct();
  const targets = targetOptions(dashboard);
  const [combo, setCombo] = useState(editing?.combo ?? "");
  const [action, setAction] = useState<Hotkey["action"]>(editing?.action ?? (apps.length ? "open" : "scene"));
  const [app, setApp] = useState(editing?.app ?? apps[0]?.app ?? "");
  const [scheme, setScheme] = useState(editing?.scene_id ?? dashboard.scenes.find((item) => !item.is_preset)?.id ?? dashboard.scenes[0]?.id ?? 0);
  const [target, setTarget] = useState(editing ? targetKey(editing.target_type, editing.target_id) : targets[0].key);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const where = targets.find((option) => option.key === target) ?? targets[0];
    const open = action === "open";
    const payload: HotkeyPayload = {
      combo, action, app: open ? app : null, scene_id: action === "scene" ? scheme : null,
      target_type: open ? "all" : where.type, target_id: open ? null : where.id, enabled: editing?.enabled ?? true,
    };
    if (await act(() => shortcuts.saveHotkey(payload, editing?.id), "That hotkey could not be saved.")) onDone();
  };

  return (
    <form className="ll-shortcut-form" onSubmit={submit}>
      <ComboInput value={combo} onChange={setCombo} />
      <select className="lv-select" value={action} aria-label="What it does" onChange={(event) => setAction(event.target.value as Hotkey["action"])}>
        {Object.entries(ACTIONS).map(([id, label]) => <option value={id} key={id} disabled={id === "open" && !apps.length}>{label}</option>)}
      </select>
      {action === "open" && (
        <select className="lv-select" value={app} aria-label="App" onChange={(event) => setApp(event.target.value)}>
          {apps.map((item) => <option value={item.app} key={item.app}>{item.label}</option>)}
        </select>
      )}
      {action === "scene" && (
        <select className="lv-select" value={scheme} aria-label="Scheme" onChange={(event) => setScheme(Number(event.target.value))}>
          {dashboard.scenes.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}
        </select>
      )}
      {action !== "open" && (
        <select className="lv-select" value={target} aria-label="On" onChange={(event) => setTarget(event.target.value)}>
          {targets.map((option) => <option value={option.key} key={`${option.label}-${option.key}`}>{option.label}</option>)}
        </select>
      )}
      <span className="ll-shortcut-buttons">
        <button className="lv-button ll-small-button" type="button" onClick={onDone}>Cancel</button>
        <button className="lv-button ll-lit-button ll-small-button" type="submit" disabled={!combo || (action === "open" && !app)}>
          <Save size={15} /> {editing ? "Save" : "Add hotkey"}
        </button>
      </span>
    </form>
  );
}

/** Rename a shortcut, recolor it, or give it the keys painted now. */
function KeyGroupForm({ group, painted, onDone }: { group?: KeyGroup; painted: string[]; onDone: () => void }) {
  const act = useShortcutAct();
  const toast = useToast();
  const [name, setName] = useState(group?.name ?? "");
  const [color, setColor] = useState(group?.color ?? "#38BDF8");
  const [usePainted, setUsePainted] = useState(!group);
  const keys = usePainted ? painted : group?.keys ?? [];
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (await act(() => shortcuts.saveKeys({ name, keys, color }, group?.id), `Could not save ${name}.`)) {
      if (!group) toast(`Saved ${name}: paint it from the group chips, or use its name in schemes`);
      onDone();
    }
  };
  return (
    <form className="ll-shortcut-form" onSubmit={submit}>
      <input className="lv-input" value={name} maxLength={40} required autoFocus pattern="[A-Za-z0-9][A-Za-z0-9 _]*" placeholder="Name, e.g. Copy paste"
        aria-label="Shortcut name" onChange={(event) => setName(event.target.value)} />
      <ColorInput label="Shortcut color" value={color} onCommit={setColor} />
      {group && (
        <Toggle label={`Use the painted keys (${painted.length})`} checked={usePainted} disabled={!painted.length} onChange={setUsePainted} />
      )}
      <Keycaps keys={keys.slice(0, 16)} />
      <span className="ll-shortcut-buttons">
        <button className="lv-button ll-small-button" type="button" onClick={onDone}>Cancel</button>
        <button className="lv-button ll-lit-button ll-small-button" type="submit" disabled={!keys.length}>
          <Save size={15} /> Save
        </button>
      </span>
    </form>
  );
}

/** Shortcut keys (your named sets of keys) and hotkeys (combinations pressed on the PC that play schemes). */
export function ShortcutsSection({ dashboard, painted }: { dashboard: Dashboard; painted: string[] }) {
  const { data, error } = useShortcuts();
  const act = useShortcutAct();
  const toast = useToast();
  const [editingKeys, setEditingKeys] = useState<number | "new" | null>(null);
  const [editingHotkey, setEditingHotkey] = useState<number | "new" | null>(null);
  const targets = useMemo(() => new Map(targetOptions(dashboard).map((option) => [option.key, option.label])), [dashboard]);

  if (error) return <p className="lv-alert lv-alert-error">Shortcuts could not be read.</p>;
  if (!data) return null;
  const listening = data.bridges.filter((bridge) => bridge.listening);
  const registered = data.hotkeys.filter((hotkey) => hotkey.enabled && !hotkey.problem).length;
  const strip = (hotkey: Hotkey) => {
    const colors = dashboard.scenes.find((scheme) => scheme.id === hotkey.scene_id)?.preview_colors ?? [];
    if (hotkey.action === "open") return "linear-gradient(90deg, #38bdf8, #8b5cf6)";
    if (hotkey.action !== "scene" || !colors.length) return "linear-gradient(90deg, #2a2a2a, #555)";
    return colors.length === 1 ? colors[0] : `linear-gradient(90deg, ${colors.slice(0, 4).join(", ")})`;
  };
  const playing = (hotkey: Hotkey) => hotkey.action === "scene" && Object.values(dashboard.playing).includes(hotkey.scene_id ?? -1);

  return (
    <section className="ll-shortcuts" aria-labelledby="shortcuts-title">
      <div className="ll-shortcuts-head">
        <h2 id="shortcuts-title">Shortcuts</h2>
        <span className="ll-meta ll-bridge">
          <span className={listening.length ? "ll-bridge-dot ll-bridge-on" : "ll-bridge-dot"} aria-hidden="true" />
          {data.bridges.length === 0
            ? "No iCUE bridge yet: hotkeys need it on your PC"
            : listening.length
              ? `iCUE bridge on ${listening.map((bridge) => bridge.host).join(", ")} · ${registered} ${registered === 1 ? "hotkey" : "hotkeys"} registered`
              : `iCUE bridge not listening: ${data.bridges[0].error ?? "checking…"}`}
        </span>
      </div>
      <div className="ll-shortcut-cards">
        <section className="ll-panel ll-shortcut-card" aria-labelledby="keys-title">
          <header>
            <div><strong id="keys-title">Shortcut keys</strong><span className="ll-meta">Your named sets of keys, used like WASD or Arrows</span></div>
            <button className="lv-button ll-small-button" type="button" disabled={!painted.length} title={painted.length ? undefined : "Paint some keys first"}
              onClick={() => setEditingKeys("new")}>
              Save painted keys
            </button>
          </header>
          {editingKeys === "new" && <KeyGroupForm painted={painted} onDone={() => setEditingKeys(null)} />}
          {data.key_groups.length ? (
            <ul className="ll-shortcut-list">
              {data.key_groups.map((group) =>
                editingKeys === group.id ? (
                  <li key={group.id}><KeyGroupForm group={group} painted={painted} onDone={() => setEditingKeys(null)} /></li>
                ) : (
                  <li key={group.id}>
                    <span className="ll-shortcut-dot" style={{ background: group.color ?? "var(--lv-muted)" }} aria-hidden="true" />
                    <strong>{group.name}</strong>
                    <Keycaps keys={group.keys.slice(0, 10)} />
                    {group.keys.length > 10 && <span className="ll-meta">+{group.keys.length - 10}</span>}
                    <button className="lv-icon-button" type="button" aria-label={`Edit ${group.name}`} title="Edit" onClick={() => setEditingKeys(group.id)}>
                      <Pencil size={15} />
                    </button>
                    <button className="lv-icon-button" type="button" aria-label={`Delete ${group.name}`} title="Delete"
                      onClick={async () => {
                        if (await act(() => shortcuts.deleteKeys(group.id), `Could not delete ${group.name}.`))
                          toast(`${group.name} deleted`, { label: "Undo", run: () => act(() => shortcuts.saveKeys({ name: group.name, keys: group.keys, color: group.color }), `Could not restore ${group.name}.`) });
                      }}>
                      <Trash2 size={15} />
                    </button>
                  </li>
                ),
              )}
            </ul>
          ) : (
            editingKeys !== "new" && <p className="lv-caption">None yet. Paint keys (Ctrl and C, say), then Save painted keys.</p>
          )}
        </section>

        <section className="ll-panel ll-shortcut-card" aria-labelledby="hotkeys-title">
          <header>
            <div><strong id="hotkeys-title">Hotkeys</strong><span className="ll-meta">Pressed anywhere on the PC: open an app, or play a scheme (again to stop)</span></div>
            <button className="lv-button ll-lit-button ll-small-button" type="button" onClick={() => setEditingHotkey("new")}>
              <Plus size={15} /> New hotkey
            </button>
          </header>
          {editingHotkey === "new" && <HotkeyForm dashboard={dashboard} apps={data.apps} onDone={() => setEditingHotkey(null)} />}
          {data.hotkeys.length > 0 ? (
            <ul className="ll-shortcut-list">
              {data.hotkeys.map((hotkey) =>
                editingHotkey === hotkey.id ? (
                  <li key={hotkey.id}><HotkeyForm dashboard={dashboard} apps={data.apps} editing={hotkey} onDone={() => setEditingHotkey(null)} /></li>
                ) : (
                  <li key={hotkey.id} className={hotkey.enabled ? undefined : "ll-shortcut-off"}>
                    <span className="ll-keycaps ll-combo-keys">{hotkey.combo.split("+").map((key) => <kbd key={key}>{key}</kbd>)}</span>
                    <span className="ll-hotkey-what">
                      <span className="ll-hotkey-strip" style={{ background: strip(hotkey) }} aria-hidden="true" />
                      <span>
                        {hotkey.action === "open"
                          ? `Open ${hotkey.app_label ?? hotkey.app}`
                          : <>
                              {hotkey.action === "scene" ? `Play ${hotkey.scene_name ?? "a deleted scheme"}` : ACTIONS[hotkey.action]}
                              {" · "}
                              {targets.get(targetKey(hotkey.target_type, hotkey.target_id)) ?? "All lights"}
                            </>}
                        {hotkey.problem && <span className="ll-hotkey-problem"> · not available: {hotkey.problem}</span>}
                      </span>
                    </span>
                    <button className="lv-button ll-small-button" type="button" onClick={() => act(() => shortcuts.press(hotkey.id))}>
                      {playing(hotkey) ? "Stop" : "Try"}
                    </button>
                    <Toggle label={`${hotkey.enabled ? "Turn off" : "Turn on"} hotkey ${hotkey.combo}`} hideLabel checked={hotkey.enabled}
                      onChange={(enabled) => act(() => shortcuts.saveHotkey({ ...hotkey, enabled }, hotkey.id))} />
                    <button className="lv-icon-button" type="button" aria-label={`Edit ${hotkey.combo}`} title="Edit" onClick={() => setEditingHotkey(hotkey.id)}>
                      <Pencil size={15} />
                    </button>
                    <button className="lv-icon-button" type="button" aria-label={`Delete ${hotkey.combo}`} title="Delete" onClick={() => act(() => shortcuts.deleteHotkey(hotkey.id))}>
                      <Trash2 size={15} />
                    </button>
                  </li>
                ),
              )}
            </ul>
          ) : (
            editingHotkey !== "new" && <p className="lv-caption">None yet: say, Ctrl+Alt+V to open VS Code, or Ctrl+Alt+G to play a gaming scheme on the keyboard.</p>
          )}
          <span className="lv-caption">
            Windows gives these combinations to Lumia instead of the app in front, so pick ones no app needs. Fn can't be one of the keys:
            the keyboard keeps it to itself. More apps can be added on the PC, in icue_bridge.json. Your assistant can set hotkeys too.
          </span>
        </section>
      </div>
    </section>
  );
}
