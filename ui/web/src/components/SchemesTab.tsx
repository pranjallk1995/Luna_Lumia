import { Circle, Pencil, Play, Plus, Save, Search, Square, Sun, Timer, Trash2 } from "lucide-react";
import { useRef, useState, type FormEvent } from "react";

import { lumia, useAct, type Dashboard, type Scheme, type Settings, type Step, type Transition } from "../api";
import { SCHEME_FILTERS, curvePoints, filterSchemes, schemeDetails, schemePayload, schemeSegments, seconds, targetOptions, temperatureSchemes, type SchemeFilter } from "../dashboard";
import { messageOf, remember, remembered } from "../lib";
import { ColorChips, ColorInput, ModeToggle, SectionHead, Slider, TemperatureChips, Toggle, type Mode } from "./controls";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

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
      <button className="lv-button lv-button-primary" type="submit">
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
        <section className="ll-step" key={step.uid} aria-label={`Step ${index + 1}`}>
          <span className="ll-step-number">Step {index + 1}</span>
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
      <button className="lv-button lv-button-primary" type="submit">
        <Save size={17} />
        {editing ? "Save changes" : "Save sequence"}
      </button>
    </form>
  );
}

/** A scheme drawn to time: each step is as wide as it holds and fades. */
function Strip({ scheme, transitions }: { scheme: Scheme; transitions: Transition[] }) {
  return (
    <div className="ll-strip" aria-hidden="true">
      {schemeSegments(scheme, transitions).map((segment, index) => (
        <i key={index} style={{ flexGrow: segment.weight, background: segment.color, opacity: segment.opacity }} />
      ))}
    </div>
  );
}

function SchemeCard({ scheme, dashboard, target, onEdit }: { scheme: Scheme; dashboard: Dashboard; target: { type: string; id: number | null }; onEdit: () => void }) {
  const act = useAct();
  const toast = useToast();
  const playingOn = Object.entries(dashboard.playing).filter(([, id]) => id === scheme.id).map(([lightId]) => Number(lightId));
  const details = `${scheme.kind === "sequence" ? "" : "Solid · "}${schemeDetails(scheme)}`;

  const stop = () =>
    act(async () => {
      for (const id of playingOn) await lumia.stopSchemes({ type: "light", id });
    });

  const remove = async () => {
    const removed = await act(() => lumia.delete("scenes", scheme.id), `Could not delete ${scheme.name}.`);
    if (removed) toast(`${scheme.name} deleted`, { label: "Undo", run: () => act(() => lumia.create("scenes", schemePayload(scheme)), `Could not restore ${scheme.name}.`) });
  };

  return (
    <article className="ll-panel ll-scheme">
      <Strip scheme={scheme} transitions={dashboard.transitions} />
      <div className="ll-scheme-name">
        <strong title={scheme.name}>{scheme.name}</strong>
        {scheme.is_preset && <span className="ll-tag">Built-in</span>}
        {Boolean(scheme.weather_slots?.length) && (
          <span className="ll-tag" title={`Plays for ${scheme.weather_slots!.map((slot) => slot.replace(/_/g, " ").replace("/", " by ")).join(", ")}`}>
            Weather
          </span>
        )}
        {Boolean(scheme.music_moods?.length) && (
          <span className="ll-tag" title={`Plays for ${scheme.music_moods!.map((mood) => `${mood} music`).join(", ")}`}>
            Music
          </span>
        )}
        {playingOn.length > 0 && <span className="ll-tag ll-tag-playing">Playing on {playingOn.length}</span>}
      </div>
      <div className="ll-meta" title={details}>
        {details}
      </div>
      <div className="ll-scheme-actions">
        <button className="lv-button ll-small-button ll-grow" type="button" onClick={() => act(() => lumia.applyScheme(scheme.id, target))}>
          <Play size={15} />
          Apply
        </button>
        {playingOn.length > 0 && (
          <button className="lv-icon-button" type="button" aria-label={`Stop ${scheme.name}`} title="Stop" onClick={stop}>
            <Square size={15} />
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
    </article>
  );
}

/** Whatever is playing, with the lights it is on and a way to stop it. */
function Playing({ dashboard }: { dashboard: Dashboard }) {
  const act = useAct();
  const ids = [...new Set(Object.values(dashboard.playing))];
  if (!ids.length) return null;
  const names = new Map(dashboard.lights.map((light) => [light.id, light.name]));
  return (
    <>
      {ids.map((schemeId) => {
        const scheme = dashboard.scenes.find(({ id }) => id === schemeId);
        const lights = Object.entries(dashboard.playing).filter(([, id]) => id === schemeId).map(([lightId]) => Number(lightId));
        return (
          <div className="ll-playing" key={schemeId}>
            <Play size={16} />
            <span className="ll-grow">
              <b>{scheme?.name ?? "A scheme"}</b> is playing on {lights.map((id) => names.get(id) ?? "a light").join(", ")}
            </span>
            <button
              className="lv-button ll-small-button"
              type="button"
              onClick={() =>
                act(async () => {
                  for (const id of lights) await lumia.stopSchemes({ type: "light", id });
                })
              }
            >
              <Square size={15} />
              Stop
            </button>
          </div>
        );
      })}
    </>
  );
}

function NewScheme({ dashboard, settings, onClose }: TabProps & { onClose: () => void }) {
  const [kind, setKind] = useState<"solid" | "sequence">(() => remembered("ll-new-scheme", ["solid", "sequence"] as const, "solid"));
  const choose = (next: "solid" | "sequence") => {
    setKind(next);
    remember("ll-new-scheme", next);
  };
  return (
    <Dialog title="New scheme" size="large" onClose={onClose}>
      <div className="lv-form">
        <div className="ll-segments" role="group" aria-label="Kind">
          <button className={kind === "solid" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={kind === "solid"} onClick={() => choose("solid")}>
            <Circle size={15} />
            Solid
          </button>
          <button className={kind === "sequence" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={kind === "sequence"} onClick={() => choose("sequence")}>
            <Timer size={15} />
            Sequence
          </button>
        </div>
        {kind === "solid" ? <SolidBuilder dashboard={dashboard} settings={settings} onSaved={onClose} /> : <SequenceBuilder dashboard={dashboard} settings={settings} onSaved={onClose} />}
      </div>
    </Dialog>
  );
}

function Library({ dashboard, settings }: TabProps) {
  const options = targetOptions(dashboard);
  const [targetKey, setTargetKey] = useState(options[0].key);
  const [filter, setFilter] = useState<SchemeFilter>("all");
  const [search, setSearch] = useState("");
  const [editing, setEditing] = useState<Scheme | null>(null);
  const [creating, setCreating] = useState(false);
  const target = options.find((option) => option.key === targetKey) ?? options[0];
  const shown = filterSchemes(dashboard.scenes, filter, search);

  return (
    <section className="ll-block" aria-labelledby="schemes-title">
      <SectionHead title="Schemes" count={dashboard.scenes.length} id="schemes-title">
        <label className="ll-target">
          Apply to
          <select className="lv-select" value={target.key} onChange={(event) => setTargetKey(event.target.value)}>
            {options.map((option) => (
              <option value={option.key} key={`${option.label}-${option.key}`}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <button className="lv-button lv-button-primary" type="button" onClick={() => setCreating(true)}>
          <Plus size={17} />
          New scheme
        </button>
      </SectionHead>
      <Playing dashboard={dashboard} />
      <div className="ll-filters">
        <div className="ll-chips" role="group" aria-label="Show">
          {SCHEME_FILTERS.map(([id, label, test]) => (
            <button className={filter === id ? "ll-choice ll-choice-active" : "ll-choice"} type="button" aria-pressed={filter === id} key={id} onClick={() => setFilter(id)}>
              {label} <span className="ll-count">{dashboard.scenes.filter(test).length}</span>
            </button>
          ))}
        </div>
        <label className="ll-search">
          <Search size={15} />
          <input className="lv-input" type="search" placeholder="Search schemes" aria-label="Search schemes" value={search} onChange={(event) => setSearch(event.target.value)} />
        </label>
      </div>
      {shown.length ? (
        <div className="ll-grid">
          {shown.map((scheme) => (
            <SchemeCard scheme={scheme} dashboard={dashboard} target={target} onEdit={() => setEditing(scheme)} key={scheme.id} />
          ))}
        </div>
      ) : (
        <p className="lv-alert">No schemes match.</p>
      )}
      {creating && <NewScheme dashboard={dashboard} settings={settings} onClose={() => setCreating(false)} />}
      {editing && (
        <Dialog title={`Edit ${editing.name}`} size="large" onClose={() => setEditing(null)}>
          {editing.kind === "sequence" ? (
            <SequenceBuilder dashboard={dashboard} settings={settings} editing={editing} onSaved={() => setEditing(null)} />
          ) : (
            <SolidBuilder dashboard={dashboard} settings={settings} editing={editing} onSaved={() => setEditing(null)} />
          )}
        </Dialog>
      )}
    </section>
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
  const toast = useToast();
  const [editing, setEditing] = useState<Transition | "new" | null>(null);

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const payload = transitionPayload(event.currentTarget);
    const saved = await act(() => (editing === "new" ? lumia.create("transitions", payload) : lumia.update("transitions", (editing as Transition).id, payload)));
    if (saved) setEditing(null);
  };

  const remove = async (item: Transition) => {
    const removed = await act(() => lumia.delete("transitions", item.id), `Could not delete ${item.name}.`);
    const { name, duration_ms, curve } = item;
    if (removed) toast(`${item.name} deleted`, { label: "Undo", run: () => act(() => lumia.create("transitions", { name, duration_ms, curve }), `Could not restore ${item.name}.`) });
  };

  return (
    <section className="ll-block" aria-labelledby="transitions-title">
      <SectionHead title="Transitions" count={dashboard.transitions.length} id="transitions-title">
        <span className="lv-caption ll-inline">How sequence steps fade into each other</span>
        <button className="lv-button" type="button" onClick={() => setEditing("new")}>
          <Plus size={17} />
          New transition
        </button>
      </SectionHead>
      <div className="ll-grid">
        {dashboard.transitions.map((item) => (
          <article className="ll-panel ll-transition" key={item.id}>
            <div className="ll-scheme-name">
              <strong>{item.name}</strong>
              {item.is_preset && <span className="ll-tag">Built-in</span>}
            </div>
            <div className="ll-meta">
              {item.duration_ms ? seconds(item.duration_ms) : "No fade"} · {item.curve}
            </div>
            <svg className="ll-curve" viewBox="0 0 100 30" preserveAspectRatio="none" aria-hidden="true">
              <line x1="0" y1="28" x2="100" y2="28" />
              <polyline points={curvePoints(item)} />
            </svg>
            {!item.is_preset && (
              <div className="ll-scheme-actions">
                <span className="ll-grow" />
                <button className="lv-icon-button" type="button" aria-label={`Edit ${item.name}`} title="Edit" onClick={() => setEditing(item)}>
                  <Pencil size={15} />
                </button>
                <button className="lv-icon-button" type="button" aria-label={`Delete ${item.name}`} title="Delete" onClick={() => remove(item)}>
                  <Trash2 size={15} />
                </button>
              </div>
            )}
          </article>
        ))}
      </div>
      {editing && (
        <Dialog title={editing === "new" ? "New transition" : `Edit ${editing.name}`} onClose={() => setEditing(null)}>
          <form className="lv-form" onSubmit={save}>
            <TransitionFields item={editing === "new" ? undefined : editing} />
            <button className="lv-button lv-button-primary" type="submit">
              <Save size={17} />
              {editing === "new" ? "Save transition" : "Save changes"}
            </button>
          </form>
        </Dialog>
      )}
    </section>
  );
}

export function SchemesTab({ dashboard, settings }: TabProps) {
  return (
    <>
      <Library dashboard={dashboard} settings={settings} />
      <Transitions dashboard={dashboard} />
    </>
  );
}
