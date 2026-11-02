import { AlarmClock, Clock, MapPin, Pencil, Plus, Save, Sun, Sunrise, Sunset, Repeat, CalendarDays, Trash2, type LucideIcon } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";

import { lumia, useAct, type Dashboard, type Schedule, type Settings } from "../api";
import {
  WHEN,
  isFinished,
  minutesOf,
  nextRun,
  scheduleAnchor,
  scheduleClock,
  scheduleDays,
  schedulePayload,
  shifted,
  targetKey,
  targetOptions,
  todayIso,
} from "../dashboard";
import { messageOf } from "../lib";
import { SectionHead, Toggle } from "./controls";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };
type When = keyof typeof WHEN;

const WHEN_ICONS: Record<When, LucideIcon> = { time: Clock, sunrise: Sunrise, sunset: Sunset };
const ACTIONS: Record<string, string> = { on: "On", off: "Off", scene: "Color scheme" };
const MIN_OFFSET = -120;
const MAX_OFFSET = 120;

function LocationDialog({ dashboard, onClose }: { dashboard: Dashboard; onClose: () => void }) {
  const act = useAct();
  const place = dashboard.location;
  const [error, setError] = useState("");

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const name = String(fields.get("name")).trim();
    if (!name) return setError("Give the location a name.");
    setError("");
    if (await act(() => lumia.saveLocation({ name, latitude: Number(fields.get("latitude")), longitude: Number(fields.get("longitude")) }))) onClose();
  };

  return (
    <Dialog title={place ? "Change location" : "Set your location"} onClose={onClose}>
      <form className="lv-form" onSubmit={submit}>
        <p className="lv-caption">
          Sunrise and sunset are worked out from latitude and longitude. Tip: right-click a place in Google Maps to copy its coordinates.
        </p>
        <label className="lv-field">
          Place
          <input className="lv-input" name="name" placeholder="Home" maxLength={80} defaultValue={place?.name ?? ""} autoFocus />
        </label>
        <div className="lv-form-row">
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
        <button className="lv-button lv-button-primary" type="submit">
          <Save size={17} />
          Save location
        </button>
      </form>
    </Dialog>
  );
}

/** The minute, refreshed each minute, so "now" and "next" stay true while the page is open. */
function useNow() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

const percentOfDay = (minutes: number) => `${(minutes / 1440) * 100}%`;
const clock = (minutes: number) => `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`;

/** Today as a strip: daylight, every schedule's time, and now. */
function Today({ dashboard, onLocation }: { dashboard: Dashboard; onLocation: () => void }) {
  const now = useNow();
  const place = dashboard.location;
  const sunrise = minutesOf(place?.sunrise);
  const sunset = minutesOf(place?.sunset);
  const current = now.getHours() * 60 + now.getMinutes();
  const next = dashboard.schedules
    .map((schedule) => ({ schedule, run: nextRun(schedule, now) }))
    .filter((item) => item.run)
    .sort((a, b) => a.run!.inMinutes - b.run!.inMinutes)[0];

  return (
    <section className="ll-panel ll-today" aria-labelledby="today-title">
      <div className="ll-today-head">
        <h2 id="today-title">
          <Sun size={16} />
          Today
        </h2>
        <span className="lv-caption">
          {next ? (
            <>
              Next up: <b>{next.schedule.name}</b> in {Math.floor(next.run!.inMinutes / 60)} h {next.run!.inMinutes % 60} min
            </>
          ) : (
            "Nothing scheduled"
          )}
        </span>
      </div>
      <div className="ll-day" role="img" aria-label={`Today's schedules${place ? `, with sunrise at ${place.sunrise} and sunset at ${place.sunset}` : ""}`}>
        {sunrise !== null && sunset !== null && <span className="ll-daylight" style={{ left: percentOfDay(sunrise), width: percentOfDay(sunset - sunrise) }} />}
        {dashboard.schedules.map((schedule) => {
          const at = minutesOf(scheduleClock(schedule));
          if (at === null) return null;
          const Icon = schedule.kind === "alarm" ? AlarmClock : WHEN_ICONS[(schedule.time_mode ?? "time") as When];
          const paused = schedule.enabled === false || isFinished(schedule);
          return (
            <span className={paused ? "ll-day-mark ll-day-mark-paused" : "ll-day-mark"} style={{ left: percentOfDay(at) }} title={`${schedule.name} · ${scheduleClock(schedule)}`} key={schedule.id}>
              <Icon size={13} />
            </span>
          );
        })}
        <span className="ll-day-now" style={{ left: percentOfDay(current) }} title={`Now, ${clock(current)}`} />
      </div>
      <div className="ll-day-axis" aria-hidden="true">
        {[0, 6, 12, 18, 24].map((hour) => (
          <span key={hour} style={{ left: percentOfDay(hour * 60) }}>
            {clock(hour * 60)}
          </span>
        ))}
      </div>
      <div className="ll-sun">
        <span>
          <MapPin size={15} />
          <b>{place?.name ?? "No location"}</b>
          <button className="ll-link-button" type="button" onClick={onLocation}>
            {place ? "Change" : "Set location"}
          </button>
        </span>
        {place && (
          <>
            <span>
              <Sunrise size={15} />
              Sunrise <b>{place.sunrise || "—"}</b>
            </span>
            <span>
              <Sunset size={15} />
              Sunset <b>{place.sunset || "—"}</b>
            </span>
          </>
        )}
        <span>
          Now <b>{clock(current)}</b>
        </span>
      </div>
    </section>
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
    <form className="lv-form" onSubmit={submit}>
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
      {when !== "time" && !dashboard.location && <p className="lv-alert">Set your location on the Today panel to schedule at sunrise or sunset.</p>}
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

function ScheduleRow({ schedule, dashboard, settings, onEdit }: TabProps & { schedule: Schedule; onEdit: () => void }) {
  const act = useAct();
  const toast = useToast();
  const now = useNow();
  const options = targetOptions(dashboard);
  const Icon = schedule.kind === "alarm" ? AlarmClock : Clock;
  const target = options.find((option) => option.key === targetKey(schedule.target_type, schedule.target_id))?.label ?? "Deleted target";
  const action =
    schedule.action === "scene" ? `plays ${dashboard.scenes.find(({ id }) => id === schedule.scene_id)?.name ?? "a deleted scheme"}` : `turns ${schedule.action}`;
  const finished = isFinished(schedule);
  const active = schedule.enabled !== false && !finished;
  const run = nextRun(schedule, now);

  const setActive = (on: boolean) =>
    act(() => lumia.update("schedules", schedule.id, schedulePayload(schedule, { enabled: on })), `Could not ${on ? "resume" : "pause"} ${schedule.name}.`).then(
      (done) => done && toast(`${schedule.name} ${on ? "resumed" : "paused"}`),
    );

  const remove = async () => {
    const removed = await act(() => lumia.delete("schedules", schedule.id), `Could not delete ${schedule.name}.`);
    if (removed) toast(`${schedule.name} deleted`, { label: "Undo", run: () => act(() => lumia.create("schedules", schedulePayload(schedule)), `Could not restore ${schedule.name}.`) });
  };

  return (
    <article className={active ? "ll-panel ll-schedule" : "ll-panel ll-schedule ll-schedule-paused"}>
      <div className="ll-clock">
        {scheduleClock(schedule)}
        <small>{scheduleAnchor(schedule, Boolean(dashboard.location))}</small>
      </div>
      <div className="ll-schedule-main">
        <strong>
          <Icon size={15} />
          <span title={schedule.name}>{schedule.name}</span>
          {schedule.kind === "alarm" && <span className="ll-tag">Alarm</span>}
          {finished ? <span className="ll-tag">Done</span> : schedule.enabled === false && <span className="ll-tag">Paused</span>}
        </strong>
        <p>
          {scheduleDays(schedule, settings.weekday_names)} · {target} · {action}
        </p>
        <p>{finished ? "Ran on its date. Edit it to set a new one." : run ? `Next: ${run.label}` : active ? "No upcoming run" : "Paused"}</p>
      </div>
      <div className="ll-schedule-side">
        <Toggle label={`${schedule.name} active`} hideLabel checked={active} disabled={finished} onChange={setActive} />
        <button className="lv-icon-button" type="button" aria-label={`Edit ${schedule.name}`} title="Edit" onClick={onEdit}>
          <Pencil size={15} />
        </button>
        <button className="lv-icon-button" type="button" aria-label={`Delete ${schedule.name}`} title="Delete" onClick={remove}>
          <Trash2 size={15} />
        </button>
      </div>
    </article>
  );
}

export function SchedulesTab({ dashboard, settings }: TabProps) {
  const [editing, setEditing] = useState<Schedule | "new" | null>(null);
  const [locating, setLocating] = useState(false);
  const sorted = [...dashboard.schedules].sort((a, b) => (minutesOf(scheduleClock(a)) ?? 1440) - (minutesOf(scheduleClock(b)) ?? 1440));
  return (
    <>
      <Today dashboard={dashboard} onLocation={() => setLocating(true)} />
      <section className="ll-block" aria-labelledby="schedules-title">
        <SectionHead title="Schedules and alarms" count={dashboard.schedules.length} id="schedules-title">
          <button className="lv-button lv-button-primary" type="button" onClick={() => setEditing("new")}>
            <Plus size={17} />
            New schedule
          </button>
        </SectionHead>
        {sorted.length ? (
          <div className="ll-schedules">
            {sorted.map((schedule) => (
              <ScheduleRow schedule={schedule} dashboard={dashboard} settings={settings} onEdit={() => setEditing(schedule)} key={schedule.id} />
            ))}
          </div>
        ) : (
          <p className="lv-alert">No schedules yet. A schedule turns lights on or off, or plays a scheme, at a time or with the sun.</p>
        )}
      </section>
      {editing && (
        <Dialog title={editing === "new" ? "New schedule or alarm" : `Edit ${editing.kind === "alarm" ? "alarm" : "schedule"}`} size="large" onClose={() => setEditing(null)}>
          <ScheduleForm dashboard={dashboard} settings={settings} editing={editing === "new" ? undefined : editing} onSaved={() => setEditing(null)} />
        </Dialog>
      )}
      {locating && <LocationDialog dashboard={dashboard} onClose={() => setLocating(false)} />}
    </>
  );
}
