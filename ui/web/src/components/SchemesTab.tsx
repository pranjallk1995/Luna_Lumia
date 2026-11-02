import { Circle, CirclePlus, Palette, Pencil, Play, Plus, Save, Square, StopCircle, Sun, Timer, Trash2, Repeat2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { lumia, useAct, type Dashboard, type Scheme, type Settings, type Step, type Transition } from "../api";
import { accent, curvePoints, schemeDetails, schemePreview, seconds, targetOptions, temperatureSchemes } from "../dashboard";
import { messageOf, remember, remembered } from "../lib";
import { ColorChips, ColorInput, ModeToggle, Slider, TemperatureChips, Toggle, type Mode } from "./controls";
import { Dialog } from "./Dialog";

type TabProps = { dashboard: Dashboard; settings: Settings };

const CURVES = ["ease-in-out", "linear", "ease-in", "ease-out"];
const FALLBACK_COLOR = "#FF8A5B";
const FALLBACK_TEMP = 2700;
const INSTANT = 0; // option value for "no transition"
const DEFAULT_TRANSITION = "Smooth";

type LightValue = { mode: Mode; color: string; temp: number };

const lightValue = (color?: string | null, temp?: number | null): LightValue => ({
  mode: color ? "color" : "temperature",
  color: color || FALLBACK_COLOR,
  temp: temp || FALLBACK_TEMP,
});

const valuePayload = ({ mode, color, temp }: LightValue) => (mode === "color" ? { color } : { color_temp: temp });

type ValueInputProps = {
  value: LightValue;
  settings: Settings;
  onChange: (value: LightValue) => void;
  /** Built-in temperatures offered as chips; leaving them out also leaves out the color chips. */
  temperatures?: Scheme[];
};

function ValueInput({ value, settings, onChange, temperatures }: ValueInputProps) {
  return (
    <div className="ll-value">
      <ModeToggle mode={value.mode} onChange={(mode) => onChange({ ...value, mode })} />
      <div className="ll-mode-body">
        {value.mode === "temperature" ? (
          <>
            <Slider
              label="Temperature"
              min={settings.min_color_temp}
              max={settings.max_color_temp}
              step={100}
              unit="K"
              value={value.temp}
              onCommit={(temp) => onChange({ ...value, temp })}
            />
            {temperatures && <TemperatureChips schemes={temperatures} onPick={(scheme) => onChange({ ...value, temp: scheme.color_temp! })} />}
          </>
        ) : (
          <div className="ll-color-row">
            <ColorInput value={value.color} onCommit={(color) => onChange({ ...value, color })} />
            {temperatures && <ColorChips settings={settings} onPick={(color) => onChange({ ...value, color })} />}
          </div>
        )}
      </div>
    </div>
  );
}

/** Save to the backend: a new one clears the form, an edit closes its dialog, a refusal stays visible. */
function useSave(editing: Scheme | undefined, onDone: () => void) {
  const act = useAct();
  const [error, setError] = useState("");
  const save = async (payload: unknown) => {
    setError("");
    await act(async () => {
      try {
        await (editing ? lumia.update("scenes", editing.id, payload) : lumia.create("scenes", payload));
        onDone();
      } catch (failure) {
        setError(messageOf(failure, "That could not be saved."));
      }
    });
  };
  return { error, setError, save };
}

function SolidBuilder({ dashboard, settings, editing, onSaved }: TabProps & { editing?: Scheme; onSaved?: () => void }) {
  const [name, setName] = useState(editing?.name ?? "");
  const [brightness, setBrightness] = useState(editing?.brightness ?? 80);
  const [value, setValue] = useState<LightValue>(editing ? lightValue(editing.color, editing.color_temp) : lightValue(null, null));
  const { error, setError, save } = useSave(editing, () => (onSaved ? onSaved() : setName("")));

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError("Give the scheme a name.");
    save({ name, kind: "solid", brightness, ...valuePayload(value) });
  };

  return (
    <form className="lv-form" onSubmit={submit}>
      <label className="lv-field">
        Name
        <input className="lv-input" placeholder="Evening glow" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <ValueInput value={value} settings={settings} onChange={setValue} temperatures={temperatureSchemes(dashboard.scenes, settings.temperature_presets)} />
      <Slider label="Brightness" icon={Sun} min={1} max={100} value={brightness} onCommit={setBrightness} />
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button" type="submit">
        <Save size={17} />
        {editing ? "Save changes" : "Save solid scheme"}
      </button>
    </form>
  );
}

type DraftStep = { uid: number; value: LightValue; brightness: number; hold: number; transition: number };

function SequenceBuilder({ dashboard, settings, editing, onSaved }: TabProps & { editing?: Scheme; onSaved?: () => void }) {
  const nextUid = useRef(0);
  const options = [
    { id: INSTANT, label: "Instant" },
    ...dashboard.transitions
      .filter((item) => item.duration_ms || item.name !== "Instant")
      .map((item) => ({ id: item.id, label: `${item.name} · ${seconds(item.duration_ms)} ${item.curve}` })),
  ];
  const known = new Set(options.map(({ id }) => id));
  const fallbackTransition = dashboard.transitions.find((item) => item.name === DEFAULT_TRANSITION)?.id ?? INSTANT;

  const blank = (): DraftStep => ({ uid: nextUid.current++, value: lightValue(null, null), brightness: 80, hold: 1, transition: fallbackTransition });
  const loaded = (step: Step): DraftStep => ({
    uid: nextUid.current++,
    value: lightValue(step.color, step.color_temp),
    brightness: step.brightness,
    hold: (step.hold_ms ?? 0) / 1000,
    // Built-in "Instant" (or a deleted transition) is the form's Instant option.
    transition: step.transition_id && known.has(step.transition_id) ? step.transition_id : INSTANT,
  });

  const [name, setName] = useState(editing?.name ?? "");
  const [loops, setLoops] = useState(editing?.loops ?? true);
  const [steps, setSteps] = useState<DraftStep[]>(() => (editing ? editing.steps.map(loaded) : [blank(), blank()]));
  const { error, setError, save } = useSave(editing, () => (onSaved ? onSaved() : setName("")));

  const patch = (uid: number, change: Partial<DraftStep>) =>
    setSteps((current) => current.map((step) => (step.uid === uid ? { ...step, ...change } : step)));

  // A new step starts from the previous step's settings.
  const addStep = () => setSteps((current) => [...current, { ...current[current.length - 1], uid: nextUid.current++ }]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError("Give the sequence a name.");
    save({
      name,
      kind: "sequence",
      loops,
      steps: steps.map(({ value, brightness, hold, transition }) => ({
        ...valuePayload(value),
        brightness,
        hold_ms: Math.round(hold * 1000),
        transition_id: transition || null,
      })),
    });
  };

  return (
    <form className="lv-form" onSubmit={submit}>
      <label className="lv-field">
        Name
        <input className="lv-input" placeholder="Aurora" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      {steps.map((step, index) => (
        <section className="ll-step ll-accent" style={accent(index)} key={step.uid} aria-label={`Step ${index + 1}`}>
          <button
            className="lv-icon-button ll-step-remove"
            type="button"
            aria-label={`Remove step ${index + 1}`}
            disabled={steps.length <= 2}
            onClick={() => setSteps((current) => current.filter(({ uid }) => uid !== step.uid))}
          >
            <Trash2 size={15} />
          </button>
          <div className="lv-form-row">
            <ValueInput value={step.value} settings={settings} onChange={(value) => patch(step.uid, { value })} />
            <Slider label="Brightness" icon={Sun} min={1} max={100} value={step.brightness} onCommit={(brightness) => patch(step.uid, { brightness })} />
          </div>
          <div className="lv-form-row">
            <label className="lv-field">
              {index > 0 ? "Fade in" : "Fade in (when looping back)"}
              <select className="lv-select" value={step.transition} onChange={(event) => patch(step.uid, { transition: Number(event.target.value) })}>
                {options.map(({ id, label }) => (
                  <option value={id} key={id}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="lv-field">
              Hold (seconds)
              <input
                className="lv-input"
                type="number"
                min="0"
                max="3600"
                step="0.1"
                value={step.hold}
                onChange={(event) => patch(step.uid, { hold: Number(event.target.value) })}
              />
            </label>
          </div>
        </section>
      ))}
      <div className="ll-sequence-row">
        <button className="lv-button" type="button" disabled={steps.length >= settings.max_sequence_steps} onClick={addStep}>
          <Plus size={17} />
          Add step
        </button>
        <Toggle label="Loop" checked={loops} onChange={setLoops} />
      </div>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button" type="submit">
        <Save size={17} />
        {editing ? "Save changes" : "Save sequence"}
      </button>
    </form>
  );
}

function Library({ dashboard, settings }: TabProps) {
  const act = useAct();
  const options = targetOptions(dashboard);
  const [targetKey, setTargetKey] = useState(options[0].key);
  const [editing, setEditing] = useState<Scheme | null>(null);
  const target = options.find((option) => option.key === targetKey) ?? options[0];
  const playing = Object.entries(dashboard.playing);

  const stopScheme = async (schemeId: number) => {
    for (const [lightId, playingId] of playing) {
      if (playingId === schemeId) await lumia.stopSchemes({ type: "light", id: Number(lightId) });
    }
  };

  return (
    <>
      <label className="lv-field ll-apply-to">
        Apply to
        <select className="lv-select" value={target.key} onChange={(event) => setTargetKey(event.target.value)}>
          {options.map((option) => (
            <option value={option.key} key={`${option.label}-${option.key}`}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      {playing.length > 0 && (
        <button className="lv-button ll-stop" type="button" onClick={() => act(() => lumia.stopSchemes({ type: "all", id: null }))}>
          <StopCircle size={17} />
          Stop all sequences
        </button>
      )}
      <div className="ll-grid">
        {dashboard.scenes.map((scheme, index) => {
          const count = playing.filter(([, id]) => id === scheme.id).length;
          const details = `${scheme.kind === "sequence" ? "Sequence" : "Solid"} · ${schemeDetails(scheme)}`;
          return (
            <article className="ll-scheme ll-accent" style={accent(index)} key={scheme.id}>
              <div className="ll-preview" style={{ background: schemePreview(scheme) }} />
              <div className="ll-scheme-body">
                <div className="ll-truncate ll-scheme-title" title={scheme.name}>
                  {scheme.name}
                </div>
                <div className="ll-badges">
                  {scheme.is_preset && <span className="ll-badge">Built-in</span>}
                  {Boolean(scheme.weather_slots?.length) && (
                    <span className="ll-badge" title={scheme.weather_slots!.map((slot) => slot.replace(/_/g, " ").replace("/", " by ")).join(", ")}>
                      Weather
                    </span>
                  )}
                  {Boolean(scheme.music_moods?.length) && (
                    <span className="ll-badge" title={scheme.music_moods!.map((mood) => `${mood} music`).join(", ")}>
                      Music
                    </span>
                  )}
                  {count > 0 && <span className="ll-badge ll-badge-playing">Playing on {count}</span>}
                </div>
                <div className="ll-truncate ll-details-line" title={details}>
                  {details}
                </div>
                <div className="ll-actions">
                  <button className="lv-button ll-grow" type="button" onClick={() => act(() => lumia.applyScheme(scheme.id, target))}>
                    <Play size={16} />
                    Apply
                  </button>
                  {count > 0 && (
                    <button className="lv-button" type="button" aria-label={`Stop ${scheme.name}`} onClick={() => act(() => stopScheme(scheme.id))}>
                      <Square size={15} />
                    </button>
                  )}
                  {!scheme.is_preset && (
                    <>
                      <button className="lv-button" type="button" aria-label={`Edit ${scheme.name}`} onClick={() => setEditing(scheme)}>
                        <Pencil size={15} />
                      </button>
                      <button className="lv-button" type="button" aria-label={`Delete ${scheme.name}`} onClick={() => act(() => lumia.delete("scenes", scheme.id))}>
                        <Trash2 size={15} />
                      </button>
                    </>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>
      {editing && (
        <Dialog title={`Edit ${editing.name}`} size="large" onClose={() => setEditing(null)}>
          {editing.kind === "sequence" ? (
            <SequenceBuilder dashboard={dashboard} settings={settings} editing={editing} onSaved={() => setEditing(null)} />
          ) : (
            <SolidBuilder dashboard={dashboard} settings={settings} editing={editing} onSaved={() => setEditing(null)} />
          )}
        </Dialog>
      )}
    </>
  );
}

function TransitionFields({ item }: { item?: Transition }) {
  return (
    <div className="lv-form-row">
      <label className="lv-field">
        Name
        <input className="lv-input" name="name" placeholder="Gentle" maxLength={60} defaultValue={item?.name} required />
      </label>
      <label className="lv-field">
        Fade (seconds)
        <input className="lv-input" name="seconds" type="number" min="0" max="600" step="0.1" defaultValue={item ? item.duration_ms / 1000 : 1} />
      </label>
      <label className="lv-field">
        Curve
        <select className="lv-select" name="curve" defaultValue={item?.curve ?? CURVES[0]}>
          {CURVES.map((curve) => (
            <option key={curve}>{curve}</option>
          ))}
        </select>
      </label>
    </div>
  );
}

const transitionPayload = (form: HTMLFormElement) => {
  const fields = new FormData(form);
  return {
    name: String(fields.get("name")),
    duration_ms: Math.round(Number(fields.get("seconds")) * 1000),
    curve: String(fields.get("curve")),
  };
};

function Transitions({ dashboard }: { dashboard: Dashboard }) {
  const act = useAct();
  const [editing, setEditing] = useState<Transition | null>(null);

  const add = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    if (await act(() => lumia.create("transitions", transitionPayload(form)))) form.reset();
  };

  const saveEdit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (await act(() => lumia.update("transitions", editing!.id, transitionPayload(event.currentTarget)))) setEditing(null);
  };

  return (
    <>
      <div className="ll-grid">
        {dashboard.transitions.map((item, index) => (
          <article className="ll-transition ll-accent" style={accent(index)} key={item.id}>
            <div className="ll-transition-name">
              <span className="ll-truncate">{item.name}</span>
              {item.is_preset && <span className="ll-badge">Built-in</span>}
            </div>
            <div className="ll-details-line">
              {seconds(item.duration_ms)} · {item.curve}
            </div>
            <svg className="ll-curve" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" y1="28" x2="100" y2="28" />
              <polyline points={curvePoints(item)} />
            </svg>
            {!item.is_preset && (
              <div className="ll-actions">
                <button className="lv-button" type="button" aria-label={`Edit ${item.name}`} onClick={() => setEditing(item)}>
                  <Pencil size={15} />
                </button>
                <button className="lv-button" type="button" aria-label={`Delete ${item.name}`} onClick={() => act(() => lumia.delete("transitions", item.id))}>
                  <Trash2 size={15} />
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      <details className="lv-panel ll-details">
        <summary>
          <CirclePlus size={17} />
          Add a transition
        </summary>
        <form className="lv-form" onSubmit={add}>
          <TransitionFields />
          <button className="lv-button" type="submit">
            Save transition
          </button>
        </form>
      </details>
      {editing && (
        <Dialog title={`Edit ${editing.name}`} onClose={() => setEditing(null)}>
          <form className="lv-form" onSubmit={saveEdit}>
            <TransitionFields item={editing} />
            <button className="lv-button" type="submit">
              <Save size={17} />
              Save changes
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}

const PARTS = [
  ["library", "Library", Palette],
  ["solid", "Solid", Circle],
  ["sequence", "Sequence", Timer],
  ["transitions", "Transitions", Repeat2],
] as const;
const PART_IDS = PARTS.map(([id]) => id);

export function SchemesTab({ dashboard, settings }: TabProps) {
  const [part, setPart] = useState(() => remembered("ll-schemes", PART_IDS, "library"));
  return (
    <>
      <div className="lv-tabs" role="tablist">
        {PARTS.map(([id, label, Icon]) => (
          <button
            className={part === id ? "lv-tab lv-tab-active" : "lv-tab"}
            type="button"
            role="tab"
            aria-selected={part === id}
            key={id}
            onClick={() => {
              setPart(id);
              remember("ll-schemes", id);
            }}
          >
            <Icon size={15} /> {label}
          </button>
        ))}
      </div>
      {part === "library" && <Library dashboard={dashboard} settings={settings} />}
      {part === "solid" && <SolidBuilder dashboard={dashboard} settings={settings} />}
      {part === "sequence" && <SequenceBuilder dashboard={dashboard} settings={settings} />}
      {part === "transitions" && <Transitions dashboard={dashboard} />}
    </>
  );
}
