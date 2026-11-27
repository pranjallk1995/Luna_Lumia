import { Eraser, Keyboard, Monitor, MousePointer2, Paintbrush, Play, Rainbow, Save, Sun } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState, type FormEvent } from "react";

import { lumia, useAct, useLightLeds, type Dashboard, type Light, type Settings } from "../api";
import { messageOf } from "../lib";
import {
  isKeyboard, isPcLight, keyLabel, paint, paintPayload, patternFromScheme, rainbow, schemeFromPattern, shown, viewBox,
  type Led, type Pattern,
} from "../pc";
import { ColorChips, ColorInput, SectionHead, Slider, Toggle } from "./controls";
import { useToast } from "./Toasts";

const KEY_SIZE = 8.6;
const LED_SIZE = 0.8;
const GROUP_LABELS: Record<string, string> = {
  wasd: "WASD", arrows: "Arrows", letters: "Letters", numbers: "Numbers", function: "F-keys",
  numpad: "Numpad", modifiers: "Modifiers", navigation: "Navigation", media: "Media",
};

/** Keys or LEDs drawn where they sit; press and drag to paint, as with a brush. */
function Surface({ leds, keyboard, pattern, onPaint }: { leds: Led[]; keyboard: boolean; pattern: Pattern; onPaint: (keys: string[]) => void }) {
  const painting = useRef(false);
  useEffect(() => {
    const stop = () => (painting.current = false);
    window.addEventListener("pointerup", stop);
    return () => window.removeEventListener("pointerup", stop);
  }, []);
  const size = keyboard ? KEY_SIZE : LED_SIZE;
  return (
    <svg className={keyboard ? "ll-pc-surface ll-pc-keyboard" : "ll-pc-surface ll-pc-strip"} viewBox={viewBox(leds, keyboard)}
      role="group" aria-label={keyboard ? "Keyboard keys" : "LEDs"} onPointerLeave={() => (painting.current = false)}>
      {leds.map((led) => (
        <g key={led.key} className="ll-pc-led"
          onPointerDown={(event) => { event.preventDefault(); painting.current = true; onPaint([led.key]); }}
          onPointerEnter={() => painting.current && onPaint([led.key])}>
          <title>{led.key}</title>
          {keyboard ? (
            <rect x={led.x - size / 2} y={led.y - size / 2} width={size} height={size} rx={1.2} fill={shown(pattern, led.key)} />
          ) : (
            <circle cx={led.x} cy={led.y} r={size / 2} fill={shown(pattern, led.key)} />
          )}
          {keyboard && (
            <text x={led.x} y={led.y + 1.1} textAnchor="middle" className="ll-pc-label">{keyLabel(led.key)}</text>
          )}
        </g>
      ))}
    </svg>
  );
}

/** One PC light: its keys or LEDs, a brush, and ways to show, save, and reuse patterns. */
function LedEditor({ light, dashboard, settings }: { light: Light; dashboard: Dashboard; settings: Settings }) {
  const act = useAct();
  const toast = useToast();
  const layout = useLightLeds(light.id);
  const leds = layout.data?.keys ?? [];
  const keyboard = isKeyboard(leds);
  const [brush, setBrush] = useState("#FF0000");
  const [erasing, setErasing] = useState(false);
  const [pattern, setPattern] = useState<Pattern>({ background: "#000000", brightness: 100, keys: {} });
  const [live, setLive] = useState(true);
  const [saving, setSaving] = useState(false);
  const timer = useRef<number | undefined>(undefined);

  // While live, every change reaches the device a moment after the last stroke.
  const send = useCallback(
    (next: Pattern) => act(() => lumia.paintLeds(light.id, paintPayload(next)), `Could not color ${light.name}.`),
    [act, light.id, light.name],
  );
  const change = (next: Pattern) => {
    setPattern(next);
    if (!live) return;
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => send(next), 250);
  };
  useEffect(() => () => window.clearTimeout(timer.current), []);

  const schemes = useMemo(() => dashboard.scenes.filter((scheme) => scheme.kind === "keys"), [dashboard.scenes]);
  const brushOn = (keys: string[]) => change(paint(pattern, keys, erasing ? pattern.background : brush));

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const name = String(new FormData(event.currentTarget).get("name") ?? "").trim();
    if (!name) return;
    if (await act(() => lumia.create("scenes", schemeFromPattern(name, pattern)), `Could not save ${name}.`)) {
      toast(`Saved ${name}: apply it here, or from Schemes, rooms and schedules`);
      setSaving(false);
    }
  };

  const Icon = keyboard ? Keyboard : leds.length <= 2 ? MousePointer2 : Monitor;
  const part = [light.zone && `zone ${light.zone}`, light.leds && `LEDs ${light.leds}`].filter(Boolean).join(" · ");

  return (
    <article className="ll-panel ll-pc-card">
      <header className="ll-pc-head">
        <h3><Icon size={16} /> {light.name}</h3>
        <span className="ll-meta">{[light.device, part, leds.length && `${leds.length} ${keyboard ? "keys" : leds.length === 1 ? "LED" : "LEDs"}`].filter(Boolean).join(" · ")}</span>
      </header>
      {layout.error ? (
        <p className="lv-alert lv-alert-error">{messageOf(layout.error, `${light.name}'s keys could not be read.`)}</p>
      ) : !layout.data ? (
        <p className="lv-caption">Reading {light.name}'s {light.protocol === "icue" ? "keys" : "LEDs"}…</p>
      ) : (
        <>
          <Surface leds={leds} keyboard={keyboard} pattern={pattern} onPaint={brushOn} />
          <div className="ll-pc-tools">
            <div className="ll-pc-brush">
              <ColorInput label="Brush color" value={brush} onCommit={(color) => { setBrush(color); setErasing(false); }} />
              <ColorChips settings={settings} onPick={(color) => { setBrush(color); setErasing(false); }} />
              <button className={erasing ? "lv-button ll-small-button ll-pc-on" : "lv-button ll-small-button"} type="button" aria-pressed={erasing} onClick={() => setErasing(!erasing)}>
                <Eraser size={15} /> Erase
              </button>
            </div>
            {Object.keys(layout.data.groups).length > 0 && (
              <div className="ll-pc-groups" role="group" aria-label="Paint a group">
                {Object.entries(layout.data.groups).map(([group, keys]) => (
                  <button className="lv-button ll-small-button" type="button" key={group} onClick={() => brushOn(keys)}>
                    {GROUP_LABELS[group] ?? group}
                  </button>
                ))}
              </div>
            )}
            <div className="ll-pc-row">
              <label className="ll-pc-field">
                Background
                <ColorInput label="Background color" value={pattern.background} onCommit={(color) => change({ ...pattern, background: color })} />
              </label>
              <button className="lv-button ll-small-button" type="button" onClick={() => change({ ...pattern, keys: Object.fromEntries(leds.map((led) => [led.key, brush])) })}>
                <Paintbrush size={15} /> Fill with brush
              </button>
              <button className="lv-button ll-small-button" type="button" onClick={() => change(rainbow(pattern, leds))}>
                <Rainbow size={15} /> Rainbow
              </button>
              <button className="lv-button ll-small-button" type="button" onClick={() => change({ ...pattern, keys: {} })}>
                Clear
              </button>
            </div>
            <Slider label={`${light.name} brightness`} icon={Sun} min={1} max={100} unit="%" value={pattern.brightness} onCommit={(brightness) => change({ ...pattern, brightness })} />
            <div className="ll-pc-row">
              <Toggle label="Live" checked={live} onChange={setLive} />
              {!live && (
                <button className="lv-button ll-small-button" type="button" onClick={() => send(pattern)}>
                  <Play size={15} /> Show on {light.name}
                </button>
              )}
              <button className="lv-button ll-small-button" type="button" onClick={() => setSaving(!saving)}>
                <Save size={15} /> Save as scheme
              </button>
            </div>
            {saving && (
              <form className="ll-pc-row" onSubmit={save}>
                <input className="lv-input" name="name" maxLength={100} placeholder="Scheme name" aria-label="Scheme name" autoFocus required />
                <button className="lv-button lv-button-primary ll-small-button" type="submit">Save</button>
              </form>
            )}
            {schemes.length > 0 && (
              <div className="ll-pc-groups" role="group" aria-label="Per-key schemes">
                <span className="ll-meta">Per-key schemes:</span>
                {schemes.map((scheme) => (
                  <span className="ll-pc-scheme" key={scheme.id}>
                    <button className="lv-button ll-small-button" type="button" title={`Play ${scheme.name} on ${light.name}`}
                      onClick={() => act(() => lumia.applyScheme(scheme.id, { type: "light", id: light.id }), `Could not play ${scheme.name}.`)}>
                      <Play size={13} /> {scheme.name}
                    </button>
                    {patternFromScheme(scheme) && (
                      <button className="ll-link-button" type="button" onClick={() => setPattern(patternFromScheme(scheme)!)}>edit</button>
                    )}
                  </span>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </article>
  );
}

/** Keyboards, mice, and case parts, each customised on its own, key by key or LED by LED. */
export function PcTab({ dashboard, settings }: { dashboard: Dashboard; settings: Settings }) {
  const pcLights = dashboard.lights.filter(isPcLight).sort((a, b) => Number(b.protocol === "icue") - Number(a.protocol === "icue") || a.name.localeCompare(b.name));
  return (
    <section aria-labelledby="pc-title">
      <SectionHead title="PC" id="pc-title" count={pcLights.length} />
      <p className="lv-caption">
        Paint keys and LEDs one by one: press and drag across them. With Live on, the device follows as you paint; save a pattern
        as a per-key scheme to play it again, from a room or a schedule. Your assistant can also design patterns and animate them.
      </p>
      {pcLights.length ? (
        <div className="ll-pc-list">
          {pcLights.map((light) => <LedEditor light={light} dashboard={dashboard} settings={settings} key={light.id} />)}
        </div>
      ) : (
        <p className="lv-alert">No PC lights yet. Add your keyboard, mouse, or motherboard under Lights, with Find PC devices.</p>
      )}
    </section>
  );
}
