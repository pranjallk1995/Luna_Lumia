import { Save, Sparkles, Sun } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { lumia, useAct, type Effect, type EffectType, type Scheme, type Settings } from "../api";
import { messageOf } from "../lib";
import { EFFECTS, effectColor } from "../pc";
import { ColorChips, ColorInput, Slider, Toggle } from "./controls";

const TWO_COLORS: EffectType[] = ["blink", "strobe", "breathe"];

/** The effect's color now, ticking at the backend's frame rate: a swatch that moves like the light will. */
export function useTicker(running: boolean) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = performance.now();
    const timer = window.setInterval(() => setT((performance.now() - started) / 1000), 120);
    return () => window.clearInterval(timer);
  }, [running]);
  return t;
}

function Swatch({ effect, base }: { effect: Effect; base: string }) {
  const t = useTicker(true);
  return <span className="ll-effect-swatch" aria-hidden="true" style={{ background: effectColor(effect, base, t) }} />;
}

/** Each effect's shape over a cycle, drawn on its button. */
const WAVES: Record<EffectType | "none", string> = {
  none: "M2 6 L20 6",
  blink: "M2 9 L2 3 L8 3 L8 9 L14 9 L14 3 L20 3",
  strobe: "M2 9 L4 2 L6 9 L11 9 L13 2 L15 9 L20 9",
  breathe: "M2 9 C6 1 8 1 11 6 S16 11 20 3",
  glow: "M2 6 C6 3 8 3 11 5 S16 8 20 4",
  rainbow: "M2 10 C5 2 17 2 20 10",
};

const Wave = ({ type }: { type: EffectType | "none" }) => (
  <svg width="22" height="12" viewBox="0 0 22 12" aria-hidden="true" className="ll-wave">
    <path d={WAVES[type]} fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const CHASE_MS = 80;

type PickerProps = {
  effect: Effect | null;
  onChange: (effect: Effect | null) => void;
  /** The color it moves from, for the preview swatch. */
  base: string;
  /** Offer a chase: each key starting a little after the one before, so a row waves. */
  keyed?: boolean;
  label?: string;
  /** Said beside the label, such as which keys move. */
  note?: string;
};

/** Choose an effect (or none), how fast it cycles, its other color, and for keys whether it chases across them. */
export function EffectPicker({ effect, onChange, base, keyed, label = "Effect", note }: PickerProps) {
  const pick = (type: EffectType | null) =>
    onChange(type ? { period_ms: 1600, ...(effect ?? {}), type, ...(type === "rainbow" || type === "glow" ? { to: null } : {}) } : null);
  const hint = note ?? (!effect ? "still colors" : EFFECTS.find((item) => item.type === effect.type)?.hint);
  return (
    <div className="ll-effect">
      <div className="ll-effect-head">
        <span>{label}</span>
        <span className="ll-meta">{hint}</span>
        {effect && <Swatch effect={effect} base={base} />}
      </div>
      <div className="ll-effect-grid" role="group" aria-label={label}>
        <button className={!effect ? "ll-effect-choice ll-effect-active" : "ll-effect-choice"} type="button" aria-pressed={!effect} onClick={() => pick(null)}>
          <Wave type="none" /> None
        </button>
        {EFFECTS.map(({ type, label: name, hint: title }) => (
          <button className={effect?.type === type ? "ll-effect-choice ll-effect-active" : "ll-effect-choice"} type="button" title={title} aria-pressed={effect?.type === type} key={type} onClick={() => pick(type)}>
            <Wave type={type} /> {name}
          </button>
        ))}
      </div>
      {effect && (
        <div className="ll-effect-body">
          <Slider label="Speed" min={0.2} max={10} step={0.1} unit=" s a cycle" value={(effect.period_ms ?? 1000) / 1000} onCommit={(value) => onChange({ ...effect, period_ms: Math.round(value * 1000) })} />
          {keyed && (
            <>
              <div className="ll-effect-row">
                <span className="ll-effect-label">Chase<small>Each key starts a little after the last</small></span>
                <Toggle label="Chase" hideLabel checked={Boolean(effect.stagger_ms)} onChange={(on) => onChange({ ...effect, stagger_ms: on ? CHASE_MS : 0 })} />
              </div>
              {Boolean(effect.stagger_ms) && (
                <Slider label="Delay per key" min={10} max={500} step={10} unit=" ms" value={effect.stagger_ms ?? CHASE_MS} onCommit={(stagger_ms) => onChange({ ...effect, stagger_ms })} />
              )}
            </>
          )}
          {TWO_COLORS.includes(effect.type) && (
            <div className="ll-effect-row">
              <span className="ll-effect-label">Second color<small>{effect.to ? "instead of dark" : effect.type === "breathe" ? "off: fades to dark" : "off: goes dark in between"}</small></span>
              {effect.to && <ColorInput label="Second color" value={effect.to} onCommit={(to) => onChange({ ...effect, to })} />}
              <Toggle label="Second color" hideLabel checked={Boolean(effect.to)} onChange={(on) => onChange({ ...effect, to: on ? "#3E6DFF" : null })} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** A scheme that moves on its own until stopped: one color, blinking, breathing, glowing, or a rainbow. */
export function EffectBuilder({ settings, editing, onSaved }: { settings: Settings; editing?: Scheme; onSaved: () => void }) {
  const act = useAct();
  const first = editing?.steps[0];
  const [name, setName] = useState(editing?.name ?? "");
  const [color, setColor] = useState(first?.color ?? "#FF2D55");
  const [brightness, setBrightness] = useState(first?.brightness ?? 100);
  const [effect, setEffect] = useState<Effect | null>(first?.effects?.[0] ?? { type: "breathe", period_ms: 3000 });
  const [error, setError] = useState("");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError("Give the scheme a name.");
    if (!effect) return setError("Pick an effect, or make a solid scheme instead.");
    setError("");
    const payload = { name, kind: "sequence", loops: true, steps: [{ color, brightness, hold_ms: 0, transition_id: null, effects: [effect] }] };
    await act(async () => {
      try {
        await (editing ? lumia.update("scenes", editing.id, payload) : lumia.create("scenes", payload));
        onSaved();
      } catch (failure) {
        setError(messageOf(failure, "That could not be saved."));
      }
    });
  };

  return (
    <form className="lv-form" onSubmit={submit}>
      <label className="lv-field">
        Name
        <input className="lv-input" placeholder="Police lights" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <div className="ll-color-row">
        <ColorInput value={color} onCommit={setColor} />
        <ColorChips settings={settings} onPick={setColor} />
      </div>
      <Slider label="Brightness" icon={Sun} min={1} max={100} value={brightness} onCommit={setBrightness} />
      <EffectPicker effect={effect} onChange={setEffect} base={color} />
      <p className="lv-caption">
        <Sparkles size={13} /> It plays until you stop it or apply another scheme. Bulbs dim rather than show dark colors, so a
        blink or breathe to dark is the strongest on them; keyboards show every color.
      </p>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button lv-button-primary" type="submit">
        <Save size={17} />
        {editing ? "Save changes" : "Save effect"}
      </button>
    </form>
  );
}

/** A one-step scheme that only moves is edited as an effect. */
export const isEffectScheme = (scheme: Scheme) => scheme.kind === "sequence" && scheme.steps.length === 1 && Boolean(scheme.steps[0].effects?.length);
