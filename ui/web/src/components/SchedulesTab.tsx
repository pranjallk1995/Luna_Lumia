import { AlarmClock, Clock, MapPin, Pencil, Save, Sunrise, Sunset, Repeat, CalendarDays, Trash2, type LucideIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { lumia, useAct, type Dashboard, type Schedule, type Settings } from "../api";
import {
  WHEN,
  accent,
  isFinished,
  scheduleAnchor,
  scheduleClock,
  scheduleDays,
  shifted,
  targetKey,
  targetOptions,
  todayIso,
} from "../dashboard";
import { messageOf } from "../lib";
import { Dialog } from "./Dialog";

type TabProps = { dashboard: Dashboard; settings: Settings };
type When = keyof typeof WHEN;

const WHEN_ICONS: Record<When, LucideIcon> = { time: Clock, sunrise: Sunrise, sunset: Sunset };
const ACTIONS: Record<string, string> = { on: "On", off: "Off", scene: "Color scheme" };
const MIN_OFFSET = -120;
const MAX_OFFSET = 120;

function Location({ dashboard }: { dashboard: Dashboard }) {
  const act = useAct();
  const place = dashboard.location;
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const name = String(fields.get("name")).trim();
    if (!name) return setError("Give the location a name.");
    setError("");
    await act(() => lumia.saveLocation({ name, latitude: Number(fields.get("latitude")), longitude: Number(fields.get("longitude")) }));
  };

  return (
    <>
      {place && (
        <div className="ll-sun">
          <MapPin size={16} />
          <strong>{place.name}</strong>
          <span>
            <Sunrise size={15} />
            Sunrise {place.sunrise || "—"}
          </span>
          <span>
            <Sunset size={15} />
            Sunset {place.sunset || "—"}
          </span>
        </div>
      )}
      <details className="lv-panel ll-details" open={!place}>
        <summary>
          <MapPin size={17} />
          {place ? "Change location" : "Set your location for sunrise & sunset"}
        </summary>
        <p className="lv-caption">
          Sunrise and sunset are calculated on this device from latitude and longitude. Tip: right-click a place in Google Maps to copy its coordinates.
        </p>
        <form className="lv-form ll-location" onSubmit={submit}>
          <div className="lv-form-row">
            <label className="lv-field">
              Place
              <input className="lv-input" name="name" placeholder="Home" maxLength={80} defaultValue={place?.name ?? ""} />
            </label>
            <label className="lv-field">
              Latitude
              <input className="lv-input" name="latitude" type="number" min="-90" max="90" step="0.0001" defaultValue={place?.latitude ?? 0} />
            </label>
            <label className="lv-field">
              Longitude
              <input className="lv-input" name="longitude" type="number" min="-180" max="180" step="0.0001" defaultValue={place?.longitude ?? 0} />
            </label>
          </div>
          {error && <p className="lv-alert lv-alert-error">{error}</p>}
          <button className="lv-button" type="submit">
            <Save size={17} />
            Save location
          </button>
        </form>
      </details>
    </>
  );
}

function ScheduleForm({ dashboard, settings, editing, onSaved }: TabProps & { editing?: Schedule; onSaved?: () => void }) {
  const act = useAct();
  const options = targetOptions(dashboard);
  const editingTarget = editing ? targetKey(editing.target_type, editing.target_id) : options[0].key;
  const schemes = dashboard.scenes;

  const [name, setName] = useState(editing?.name ?? "");
  const [kind, setKind] = useState(editing?.kind ?? "schedule");
  const [when, setWhen] = useState<When>(editing?.time_mode ?? "time");
  const [time, setTime] = useState((editing?.run_time ?? "07:00").slice(0, 5));
  const [offset, setOffset] = useState(editing?.offset_minutes ?? 0);
  const [target, setTarget] = useState(options.some((option) => option.key === editingTarget) ? editingTarget : options[0].key);
  const [action, setAction] = useState(editing?.action ?? "on");
  const [scheme, setScheme] = useState(
    editing?.scene_id && schemes.some(({ id }) => id === editing.scene_id) ? editing.scene_id : (schemes[0]?.id ?? 0),
  );
  const [once, setOnce] = useState(Boolean(editing?.run_date));
  const [days, setDays] = useState<number[]>(editing && !editing.run_date ? editing.weekdays : [0, 1, 2, 3, 4, 5, 6]);
  const [runDate, setRunDate] = useState(editing?.run_date ?? todayIso());
  const [error, setError] = useState("");

  const toggleDay = (day: number) =>
    setDays((current) => (current.includes(day) ? current.filter((other) => other !== day) : [...current, day].sort()));

  const preview = when === "time" ? null : shifted(dashboard.location?.[when], offset);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError("Give the schedule a name.");
    setError("");
    const chosen = options.find((option) => option.key === target)!;
    // Saving a one-time schedule that has run arms it again for its (new) date.
    const enabled = editing ? (editing.enabled ?? true) || (once && isFinished(editing)) : true;
    const payload = {
      name,
      kind,
      target_type: chosen.type,
      target_id: chosen.id,
      action,
      scene_id: action === "scene" ? scheme : null,
      time_mode: when,
      run_time: when === "time" ? `${time}:00` : null,
      offset_minutes: when === "time" ? 0 : offset,
      weekdays: days,
      run_date: once ? runDate : null,
      enabled,
    };
    await act(async () => {
      try {
        await (editing ? lumia.update("schedules", editing.id, payload) : lumia.create("schedules", payload));
        if (onSaved) onSaved();
        else setName("");
      } catch (failure) {
        setError(messageOf(failure, "That could not be saved."));
      }
    });
  };

  return (
    <form className={editing ? "lv-form" : "lv-form lv-panel"} onSubmit={submit}>
      {!editing && <h2>New schedule or alarm</h2>}
      <div className="ll-form-2-1">
        <label className="lv-field">
          Name
          <input className="lv-input" placeholder="Wake up" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
        </label>
        <label className="lv-field">
          Type
          <select className="lv-select" value={kind} onChange={(event) => setKind(event.target.value)}>
            <option value="schedule">Schedule</option>
            <option value="alarm">Alarm</option>
          </select>
        </label>
      </div>
      <div className="lv-form-row ll-align-end">
        <div className="lv-field">
          When
          <div className="ll-segments ll-segments-wide" role="group" aria-label="When">
            {(Object.keys(WHEN) as When[]).map((id) => {
              const Icon = WHEN_ICONS[id];
              return (
                <button className={when === id ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={when === id} key={id} onClick={() => setWhen(id)}>
                  <Icon size={15} />
                  {WHEN[id]}
                </button>
              );
            })}
          </div>
        </div>
        {when === "time" ? (
          <label className="lv-field">
            Time
            <input className="lv-input" type="time" value={time} required onChange={(event) => setTime(event.target.value)} />
          </label>
        ) : (
          <label className="lv-field">
            Offset from {when}: {offset} min
            <input type="range" min={MIN_OFFSET} max={MAX_OFFSET} step={5} value={offset} onChange={(event) => setOffset(Number(event.target.value))} />
          </label>
        )}
      </div>
      {preview && when !== "time" && (
        <p className="lv-caption">
          Runs {offset ? `${Math.abs(offset)} min ${offset < 0 ? "before" : "after"} ${when}` : `at ${when}`} — {preview} today, adjusting daily with the sun.
        </p>
      )}
      {when !== "time" && !dashboard.location && <p className="lv-alert">Set your location above to schedule at sunrise or sunset.</p>}
      <div className="lv-form-row">
        <label className="lv-field">
          Target
          <select className="lv-select" value={target} onChange={(event) => setTarget(event.target.value)}>
            {options.map((option) => (
              <option value={option.key} key={`${option.label}-${option.key}`}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="lv-field">
          Action
          <select className="lv-select" value={action} onChange={(event) => setAction(event.target.value)}>
            {Object.entries(ACTIONS).map(([id, label]) => (
              <option value={id} key={id}>
                {label}
              </option>
            ))}
          </select>
        </label>
      </div>
      {action === "scene" && (
        <label className="lv-field">
          Color scheme
          <select className="lv-select" value={scheme} onChange={(event) => setScheme(Number(event.target.value))}>
            {schemes.map(({ id, name: schemeName }) => (
              <option value={id} key={id}>
                {schemeName}
              </option>
            ))}
          </select>
        </label>
      )}
      <div className="ll-form-1-2 ll-align-end">
        <div className="lv-field">
          Repeat
          <div className="ll-segments ll-segments-wide" role="group" aria-label="Repeat">
            <button className={once ? "ll-segment" : "ll-segment ll-segment-active"} type="button" aria-pressed={!once} onClick={() => setOnce(false)}>
              <Repeat size={15} />
              Repeat
            </button>
            <button className={once ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={once} onClick={() => setOnce(true)}>
              <CalendarDays size={15} />
              Once
            </button>
          </div>
        </div>
        {once ? (
          <label className="lv-field">
            Date
            <input
              className="lv-input"
              type="date"
              value={runDate}
              min={runDate < todayIso() ? runDate : todayIso()}
              required
              onChange={(event) => setRunDate(event.target.value)}
            />
          </label>
        ) : (
          <div className="lv-field">
            Repeat on
            <div className="ll-chips" role="group" aria-label="Repeat on">
              {settings.weekday_names.map((label, day) => (
                <button className={days.includes(day) ? "ll-choice ll-choice-active" : "ll-choice"} type="button" aria-pressed={days.includes(day)} key={label} onClick={() => toggleDay(day)}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>
      {once && <p className="lv-caption">Runs once on this day, then switches itself off.</p>}
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button" type="submit">
        <Save size={17} />
        {editing ? "Save changes" : "Save schedule"}
      </button>
    </form>
  );
}

function ScheduleCard({ schedule, index, dashboard, settings, onEdit }: TabProps & { schedule: Schedule; index: number; onEdit: () => void }) {
  const act = useAct();
  const options = targetOptions(dashboard);
  const Icon = schedule.kind === "alarm" ? AlarmClock : Clock;
  const target = options.find((option) => option.key === targetKey(schedule.target_type, schedule.target_id))?.label ?? "Deleted target";
  const action =
    schedule.action === "scene"
      ? (dashboard.scenes.find(({ id }) => id === schedule.scene_id)?.name ?? "Deleted scheme")
      : `Turn ${schedule.action}`;
  const chips = [scheduleDays(schedule, settings.weekday_names), target, action];

  return (
    <article className="ll-schedule ll-accent" style={accent(index)}>
      <div className="ll-schedule-name">
        <Icon size={16} />
        <span className="ll-truncate" title={schedule.name}>
          {schedule.name}
        </span>
        <span className="ll-badge">{schedule.kind === "alarm" ? "Alarm" : "Schedule"}</span>
        {isFinished(schedule) ? <span className="ll-badge">Done</span> : schedule.enabled === false && <span className="ll-badge">Paused</span>}
      </div>
      <div className="ll-clock">{scheduleClock(schedule)}</div>
      <div className="ll-details-line">{scheduleAnchor(schedule, Boolean(dashboard.location))}</div>
      <div className="ll-schedule-chips">
        {chips.map((chip, chipIndex) => (
          <span className="ll-schedule-chip" title={chip} key={chipIndex}>
            {chip}
          </span>
        ))}
      </div>
      <div className="ll-actions">
        <button className="lv-button ll-small" type="button" aria-label={`Edit ${schedule.name}`} onClick={onEdit}>
          <Pencil size={15} />
        </button>
        <button className="lv-button ll-small" type="button" aria-label={`Delete ${schedule.name}`} onClick={() => act(() => lumia.delete("schedules", schedule.id))}>
          <Trash2 size={15} />
        </button>
      </div>
    </article>
  );
}

export function SchedulesTab({ dashboard, settings }: TabProps) {
  const [editing, setEditing] = useState<Schedule | null>(null);
  return (
    <>
      <Location dashboard={dashboard} />
      {dashboard.schedules.length > 0 && (
        <div className="ll-grid ll-schedules">
          {dashboard.schedules.map((schedule, index) => (
            <ScheduleCard schedule={schedule} index={index} dashboard={dashboard} settings={settings} onEdit={() => setEditing(schedule)} key={schedule.id} />
          ))}
        </div>
      )}
      <ScheduleForm dashboard={dashboard} settings={settings} />
      {editing && (
        <Dialog title={`Edit ${editing.kind === "alarm" ? "alarm" : "schedule"}`} size="large" onClose={() => setEditing(null)}>
          <ScheduleForm dashboard={dashboard} settings={settings} editing={editing} onSaved={() => setEditing(null)} />
        </Dialog>
      )}
    </>
  );
}
