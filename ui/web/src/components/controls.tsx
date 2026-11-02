/** Inputs shared by the tabs. Sliders and color pickers report only a finished choice. */

import { Check, Palette, Pencil, Thermometer, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent, type ReactNode } from "react";

import type { Light, Scheme, Settings } from "../api";
import { isValidName, rgb } from "../dashboard";

type SliderProps = {
  label: string;
  icon?: LucideIcon;
  value: number;
  min: number;
  max: number;
  step?: number;
  unit?: string;
  disabled?: boolean;
  /** Sent when the thumb is let go, so a drag is one change to the bulb and not fifty. */
  onCommit: (value: number) => void;
};

export function Slider({ label, icon: Icon, value, min, max, step = 1, unit = "", disabled, onCommit }: SliderProps) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const commit = () => {
    if (draft !== value) onCommit(draft);
  };
  return (
    <div className="ll-slider">
      {Icon && <Icon size={17} aria-hidden="true" />}
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={draft}
        disabled={disabled}
        onChange={(event) => setDraft(Number(event.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
        onBlur={commit}
      />
      <output>
        {draft}
        {unit}
      </output>
    </div>
  );
}

export function ColorInput({ value, disabled, onCommit, label = "Color" }: { value: string; disabled?: boolean; onCommit: (color: string) => void; label?: string }) {
  const ref = useRef<HTMLInputElement>(null);
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);

  // React's onChange fires on every drag; the native change event fires once, when the picker closes.
  useEffect(() => {
    const input = ref.current;
    if (!input) return;
    const finished = () => onCommit(input.value.toUpperCase());
    input.addEventListener("change", finished);
    return () => input.removeEventListener("change", finished);
  }, [onCommit]);

  return (
    <input
      ref={ref}
      className="ll-color"
      type="color"
      aria-label={label}
      value={draft.toLowerCase()}
      disabled={disabled}
      onChange={(event) => setDraft(event.target.value)}
    />
  );
}

/** A switch; ``hideLabel`` keeps the label for screen readers only, for cards where the name says it. */
export function Toggle({ label, checked, disabled, hideLabel, onChange }: { label: string; checked: boolean; disabled?: boolean; hideLabel?: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="ll-toggle">
      <input type="checkbox" role="switch" checked={checked} disabled={disabled} onChange={(event) => onChange(event.target.checked)} />
      <span aria-hidden="true" />
      <b className={hideLabel ? "ll-sr" : undefined}>{label}</b>
    </label>
  );
}

export type Mode = "temperature" | "color";

export function ModeToggle({ mode, onChange }: { mode: Mode; onChange: (mode: Mode) => void }) {
  const options: [Mode, string, LucideIcon][] = [
    ["temperature", "Temperature", Thermometer],
    ["color", "Color", Palette],
  ];
  return (
    <div className="ll-segments" role="group" aria-label="Light mode">
      {options.map(([id, label, Icon]) => (
        <button
          className={mode === id ? "ll-segment ll-segment-active" : "ll-segment"}
          type="button"
          key={id}
          aria-label={label}
          aria-pressed={mode === id}
          onClick={() => onChange(id)}
        >
          <Icon size={16} />
        </button>
      ))}
    </div>
  );
}

/** Tint a chip with a color, like the light pills on the Rooms tab. */
export function Chip({ color, children, disabled, onClick }: { color: string; children: ReactNode; disabled?: boolean; onClick: () => void }) {
  const tint = rgb(color);
  return (
    <button
      className="ll-chip"
      type="button"
      disabled={disabled}
      style={{ color, background: `rgba(${tint},.14)`, borderColor: `rgba(${tint},.38)` }}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

export function ColorChips({ settings, disabled, onPick }: { settings: Settings; disabled?: boolean; onPick: (color: string) => void }) {
  return (
    <div className="ll-chips">
      {Object.entries(settings.preset_colors).map(([hex, label]) => (
        <Chip color={hex} key={hex} disabled={disabled} onClick={() => onPick(hex)}>
          {label}
        </Chip>
      ))}
    </div>
  );
}

export function TemperatureChips({ schemes, disabled, onPick }: { schemes: Scheme[]; disabled?: boolean; onPick: (scheme: Scheme) => void }) {
  return (
    <div className="ll-chips">
      {schemes.map((scheme) => (
        <Chip color={scheme.preview_colors?.[0] ?? "#f5f5f5"} key={scheme.id} disabled={disabled} onClick={() => onPick(scheme)}>
          {scheme.name}
        </Chip>
      ))}
    </div>
  );
}

/** Choose some lights by toggling each one. */
export function LightChoice({ lights, chosen, onChange }: { lights: Light[]; chosen: number[]; onChange: (ids: number[]) => void }) {
  return (
    <div className="ll-chips" role="group" aria-label="Lights">
      {lights.map(({ id, name }) => (
        <button
          className={chosen.includes(id) ? "ll-choice ll-choice-active" : "ll-choice"}
          type="button"
          key={id}
          aria-pressed={chosen.includes(id)}
          onClick={() => onChange(chosen.includes(id) ? chosen.filter((other) => other !== id) : [...chosen, id])}
        >
          {name}
        </button>
      ))}
    </div>
  );
}

type NameEditorProps = {
  name: string;
  entity: string;
  maxChars: number;
  onRename: (name: string) => Promise<boolean>;
};

/** A name that turns into an inline rename form when clicked. */
export function NameEditor({ name, entity, maxChars, onRename }: NameEditorProps) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState("");

  if (draft === null) {
    return (
      <span className="ll-name-row">
        <span className="ll-name" title={name}>
          {name}
        </span>
        <button className="lv-icon-button ll-rename" type="button" aria-label={`Rename ${name}`} title="Rename" onClick={() => setDraft(name)}>
          <Pencil size={14} />
        </button>
      </span>
    );
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!isValidName(draft)) {
      setError(`${entity} name may contain only letters, numbers, and spaces.`);
      return;
    }
    if (draft.trim() === name || (await onRename(draft.trim()))) setDraft(null);
  };

  return (
    <form className="ll-name-form" onSubmit={submit}>
      <input
        className="lv-input"
        aria-label={`${entity} name`}
        autoFocus
        maxLength={maxChars}
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape") setDraft(null);
        }}
      />
      <button className="lv-icon-button" type="submit" aria-label="Save name">
        <Check size={17} />
      </button>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
    </form>
  );
}

/** A section title with a count and its actions on the right. */
export function SectionHead({ title, count, id, children }: { title: string; count?: number; id: string; children?: ReactNode }) {
  return (
    <div className="ll-section-head">
      <h2 id={id}>
        {title}
        {count !== undefined && <span className="ll-count">{count}</span>}
      </h2>
      {children && <div className="ll-head-actions">{children}</div>}
    </div>
  );
}

/** A light's current color as a bulb: lit, dim when off, struck through when offline. */
export function Bulb({ color, state, small }: { color: string; state: "on" | "off" | "offline"; small?: boolean }) {
  return <span className={`ll-bulb ll-bulb-${state}${small ? " ll-bulb-small" : ""}`} style={{ "--bulb": color } as React.CSSProperties} aria-hidden="true" />;
}
