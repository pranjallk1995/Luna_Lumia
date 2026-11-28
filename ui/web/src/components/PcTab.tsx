import { Eraser, Keyboard, Monitor, MousePointer2, Paintbrush, Play, Rainbow, Sun } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { lumia, useAct, useLightLeds, useShortcuts, type Dashboard, type Light, type Settings } from "../api";
import { messageOf, remember, remembered } from "../lib";
import {
  isKeyboard, isPcLight, keyLabel, keyRects, keyUnit, paint, paintPayload, patternFromScheme, rainbow, shown, viewBox, effectsFromScheme,
  type Led, type Pattern,
} from "../pc";
import { ColorInput, SectionHead, Slider, Toggle } from "./controls";
import { MotionControls, SaveScene, ShortcutsSection, usePatternMotion } from "./Shortcuts";

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
  const rects = useMemo(() => (keyboard ? keyRects(leds) : leds.map((led) => ({ ...led, w: LED_SIZE, h: LED_SIZE }))), [leds, keyboard]);
  const unit = useMemo(() => (keyboard ? keyUnit(leds) : 1), [leds, keyboard]);
  return (
    <svg className={keyboard ? "ll-pc-surface ll-pc-keyboard" : "ll-pc-surface ll-pc-strip"} viewBox={viewBox(leds, keyboard)}
      role="group" aria-label={keyboard ? "Keyboard keys" : "LEDs"} onPointerLeave={() => (painting.current = false)}>
      {rects.map((led) => (
        <g key={led.key} className="ll-pc-led"
          onPointerDown={(event) => { event.preventDefault(); painting.current = true; onPaint([led.key]); }}
          onPointerEnter={() => painting.current && onPaint([led.key])}>
          <title>{led.key}</title>
          {keyboard ? (
            <rect x={led.x - led.w / 2} y={led.y - led.h / 2} width={led.w} height={led.h} rx={unit * 0.12} fill={shown(pattern, led.key)} />
          ) : (
            <circle cx={led.x} cy={led.y} r={led.w / 2} fill={shown(pattern, led.key)} />
          )}
          {keyboard && (
            <text x={led.x} y={led.y} dy="0.35em" textAnchor="middle" fontSize={unit * 0.3} className="ll-pc-label">{keyLabel(led.key)}</text>
          )}
        </g>
      ))}
    </svg>
  );
}

/** One PC light: its keys or LEDs on the left; the brush, its effect, and saving on the right. */
function LedEditor({ light, dashboard, settings }: { light: Light; dashboard: Dashboard; settings: Settings }) {
  const act = useAct();
  const layout = useLightLeds(light.id);
  const mine = useShortcuts().data?.key_groups ?? [];
  const leds = layout.data?.keys ?? [];
  const keyboard = isKeyboard(leds);
  const [brush, setBrush] = useState("#FF0000");
  const [erasing, setErasing] = useState(false);
  const [pattern, setPattern] = useState<Pattern>({ background: "#000000", brightness: 100, keys: {} });
  const [live, setLive] = useState(true);
  const groups = useMemo(() => layout.data?.groups ?? {}, [layout.data]);
  // What moves on the pattern: drawn here as it will play; the device shows it once saved and played.
  const motion = usePatternMotion(leds, pattern, groups);
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
  const pickBrush = (color: string) => { setBrush(color.toUpperCase()); setErasing(false); };
  const yours = new Map(mine.map((group) => [group.name.toLowerCase(), group]));
  const brushName = settings.preset_colors[brush] ?? settings.preset_colors[brush.toLowerCase()] ?? brush;

  if (layout.error) return <p className="lv-alert lv-alert-error">{messageOf(layout.error, `${light.name}'s keys could not be read.`)}</p>;
  if (!layout.data) return <p className="lv-caption">Reading {light.name}'s {light.protocol === "icue" ? "keys" : "LEDs"}…</p>;

  return (
    <div className="ll-pc-layout">
      <div className="ll-pc-main">
        <div className="ll-pc-title">
          <h2>{light.name}</h2>
          <span className="ll-meta">Press and drag across {keyboard ? "keys" : "LEDs"} to paint them</span>
        </div>
        <Surface leds={leds} keyboard={keyboard} pattern={motion.shown} onPaint={brushOn} />
        {Object.keys(groups).length > 0 && (
          <div className="ll-pc-groups" role="group" aria-label="Paint a group">
            <span className="ll-meta">Paint a group</span>
            {Object.entries(groups).map(([group, keys]) => {
              const own = yours.get(group);
              return (
                <button className={own ? "ll-pc-chip ll-pc-chip-mine" : "ll-pc-chip"} type="button" key={group} onClick={() => brushOn(keys)}
                  title={own ? `Your shortcut keys: ${keys.join(", ")}` : undefined}>
                  {own && <span className="ll-shortcut-dot" style={{ background: own.color ?? "var(--lv-muted)" }} aria-hidden="true" />}
                  {own?.name ?? GROUP_LABELS[group] ?? group}
                </button>
              );
            })}
          </div>
        )}
        {keyboard && <span className="lv-caption">Dashed chips are your shortcut keys; save the keys you just painted as one below.</span>}
        {schemes.length > 0 && (
          <div className="ll-pc-groups" role="group" aria-label="Per-key schemes">
            <span className="ll-meta">Per-key schemes</span>
            {schemes.map((scheme) => (
              <span className="ll-pc-scheme" key={scheme.id}>
                <button className="ll-pc-chip" type="button" title={`Play ${scheme.name} on ${light.name}`}
                  onClick={() => act(() => lumia.applyScheme(scheme.id, { type: "light", id: light.id }), `Could not play ${scheme.name}.`)}>
                  <Play size={13} /> {scheme.name}
                </button>
                {patternFromScheme(scheme) && (
                  <button className="ll-link-button" type="button" onClick={() => { setPattern(patternFromScheme(scheme)!); motion.load(effectsFromScheme(scheme)); }}>edit</button>
                )}
              </span>
            ))}
          </div>
        )}
        <ShortcutsSection dashboard={dashboard} painted={Object.keys(pattern.keys)} />
      </div>

      <aside className="ll-panel ll-pc-panel" aria-label="Brush">
        <div className="ll-pc-brush-head">
          <div><span className="ll-meta">{erasing ? "Eraser" : "Brush"}</span><strong>{erasing ? "Background" : brushName}</strong></div>
          <ColorInput label="Brush color" value={brush} onCommit={pickBrush} />
        </div>
        <div className="ll-segments" role="group" aria-label="Tool">
          <button className={!erasing ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={!erasing} onClick={() => setErasing(false)}>
            <Paintbrush size={15} /> Brush
          </button>
          <button className={erasing ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={erasing} onClick={() => setErasing(true)}>
            <Eraser size={15} /> Eraser
          </button>
        </div>
        <div className="ll-pc-swatches" role="group" aria-label="Brush colors">
          {Object.entries(settings.preset_colors).slice(0, 12).map(([hex, label]) => (
            <button type="button" key={hex} aria-label={label} title={label} style={{ background: hex }}
              className={!erasing && hex.toUpperCase() === brush ? "ll-pc-swatch ll-pc-swatch-on" : "ll-pc-swatch"} onClick={() => pickBrush(hex)} />
          ))}
        </div>
        <label className="ll-pc-field ll-pc-wide">
          <span>Background <small className="ll-meta">unpainted {keyboard ? "keys" : "LEDs"}</small></span>
          <ColorInput label="Background color" value={pattern.background} onCommit={(color) => change({ ...pattern, background: color })} />
        </label>
        <Slider label="Brightness" icon={Sun} min={1} max={100} unit="%" value={pattern.brightness} onCommit={(brightness) => change({ ...pattern, brightness })} />
        <div className="ll-pc-actions">
          <button className="lv-button" type="button" onClick={() => change({ ...pattern, keys: Object.fromEntries(leds.map((led) => [led.key, brush])) })}>
            Fill all
          </button>
          <button className="lv-button" type="button" onClick={() => change(rainbow(pattern, leds))}>
            <Rainbow size={15} /> Rainbow
          </button>
          <button className="lv-button" type="button" onClick={() => change({ ...pattern, keys: {} })}>
            Clear
          </button>
        </div>
        <div className="ll-effect-row">
          <span className="ll-effect-label">Live<small>{live ? `${light.name} follows as you paint` : "paint here, then show it"}</small></span>
          <Toggle label="Live" hideLabel checked={live} onChange={setLive} />
        </div>
        {!live && (
          <button className="lv-button" type="button" onClick={() => send(pattern)}>
            <Play size={15} /> Show on {light.name}
          </button>
        )}
        <MotionControls pattern={pattern} groups={groups} motion={motion} keyboard={keyboard} />
        <SaveScene light={light} pattern={pattern} motion={motion} />
      </aside>
    </div>
  );
}

const PC_DEVICE = "ll-pc-device";

/** Keyboards, mice, and case parts, one at a time, painted key by key or LED by LED; then shortcut keys and hotkeys. */
export function PcTab({ dashboard, settings }: { dashboard: Dashboard; settings: Settings }) {
  const pcLights = dashboard.lights.filter(isPcLight).sort((a, b) => Number(b.protocol === "icue") - Number(a.protocol === "icue") || a.name.localeCompare(b.name));
  const ids = pcLights.map((light) => String(light.id));
  const [chosen, setChosen] = useState(() => remembered(PC_DEVICE, ids, ids[0] ?? ""));
  const light = pcLights.find((item) => String(item.id) === chosen) ?? pcLights[0];
  const choose = (id: number) => {
    setChosen(String(id));
    remember(PC_DEVICE, String(id));
  };

  return (
    <section className="ll-pc" aria-labelledby="pc-title">
      <SectionHead title="PC" id="pc-title" count={pcLights.length} />
      {pcLights.length ? (
        <>
          <div className="ll-pc-devices" role="group" aria-label="PC devices">
            {pcLights.map((item) => {
              const Icon = item.protocol === "icue" ? (/mouse/i.test(`${item.name} ${item.device}`) ? MousePointer2 : Keyboard) : Monitor;
              const part = [item.zone && `zone ${item.zone}`, item.leds && `LEDs ${item.leds}`].filter(Boolean).join(" · ");
              return (
                <button className={item.id === light.id ? "ll-pc-device ll-pc-device-on" : "ll-pc-device"} type="button" key={item.id}
                  aria-pressed={item.id === light.id} onClick={() => choose(item.id)}>
                  <span className="ll-pc-device-swatch" style={{ background: item.color }} aria-hidden="true"><Icon size={17} /></span>
                  <span>
                    <strong>{item.name}</strong>
                    <span className="ll-meta">{[item.protocol === "icue" ? "iCUE" : "OpenRGB", item.device, part].filter(Boolean).join(" · ")}</span>
                  </span>
                </button>
              );
            })}
          </div>
          <LedEditor light={light} dashboard={dashboard} settings={settings} key={light.id} />
        </>
      ) : (
        <>
          <p className="lv-alert">No PC lights yet. Add your keyboard, mouse, or motherboard under Devices, with Find PC devices.</p>
          <ShortcutsSection dashboard={dashboard} painted={[]} />
        </>
      )}
    </section>
  );
}
