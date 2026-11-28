import { AlarmClock, Clock, MapPin, Plus, Save, Sun, Sunrise, Sunset, Repeat, CalendarDays, Trash2, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";

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
  schemeSegments,
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
const MIN_OFFSET = -120;
const MAX_OFFSET = 120;

export function LocationDialog({ dashboard, onClose }: { dashboard: Dashboard; onClose: () => void }) {
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

/** What a schedule does, as one choice: turn on, turn off, or play a scheme. */
const doKey = (action: string, schemeId?: number | null) => (action === "scene" ? `scene:${schemeId}` : action);

/** A scheme's colors as a short strip; on is amber, off is dark. */
function DoStrip({ dashboard, schedule }: { dashboard: Dashboard; schedule: Pick<Schedule, "action" | "scene_id"> }) {
  const scheme = schedule.action === "scene" ? dashboard.scenes.find(({ id }) => id === schedule.scene_id) : undefined;
  return (
    <span className="ll-do-strip" aria-hidden="true">
      {scheme ? (
        schemeSegments(scheme, dashboard.transitions).map((segment, index) => (
          <i key={index} style={{ flexGrow: segment.weight, background: segment.color, opacity: segment.opacity }} />
        ))
      ) : (
        <i style={{ flexGrow: 1, background: schedule.action === "on" ? "var(--ll-lit)" : "#2a2a2a" }} />
      )}
    </span>
  );
}

/** The editor beside the list: a new schedule, or the one selected. */
function ScheduleForm({ dashboard, settings, editing, onSaved, onDeleted }: TabProps & { editing?: Schedule; onSaved: (name: string) => void; onDeleted: () => void }) {
  const act = useAct();
  const toast = useToast();
  const options = targetOptions(dashboard);
  const editingTarget = editing ? targetKey(editing.target_type, editing.target_id) : options[0].key;
  const schemes = [...dashboard.scenes].sort((a, b) => Number(a.is_preset) - Number(b.is_preset) || a.name.localeCompare(b.name));

  const [name, setName] = useState(editing?.name ?? "");
  const [kind, setKind] = useState(editing?.kind ?? "schedule");
  const [when, setWhen] = useState<When>(editing?.time_mode ?? "time");
  const [time, setTime] = useState((editing?.run_time ?? "07:00").slice(0, 5));
  const [offset, setOffset] = useState(editing?.offset_minutes ?? 0);
  const [target, setTarget] = useState(options.some((option) => option.key === editingTarget) ? editingTarget : options[0].key);
  const [what, setWhat] = useState(editing ? doKey(editing.action, editing.scene_id) : "on");
  const [once, setOnce] = useState(Boolean(editing?.run_date));
  const [days, setDays] = useState<number[]>(editing && !editing.run_date ? editing.weekdays : [0, 1, 2, 3, 4, 5, 6]);
  const [runDate, setRunDate] = useState(editing?.run_date ?? todayIso());
  const [error, setError] = useState("");

  const toggleDay = (day: number) =>
    setDays((current) => (current.includes(day) ? current.filter((other) => other !== day) : [...current, day].sort()));

  const preview = when === "time" ? null : shifted(dashboard.location?.[when], offset);
  // Rooms, groups, and every light: the places a schedule can act on, as chips; single lights in a menu.
  const places = options.filter((option) => option.type !== "light");
  const lights = options.filter((option) => option.type === "light");

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError("Give the schedule a name.");
    if (!once && !days.length) return setError("Choose at least one day.");
    setError("");
    const chosen = options.find((option) => option.key === target)!;
    const [action, schemeId] = what.startsWith("scene:") ? ["scene", Number(what.slice(6))] : [what, null];
    // Saving a one-time schedule that has run arms it again for its (new) date.
    const enabled = editing ? (editing.enabled ?? true) || (once && isFinished(editing)) : true;
    const payload = {
      name,
      kind,
      target_type: chosen.type,
      target_id: chosen.id,
      action,
      scene_id: schemeId,
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
        onSaved(name);
      } catch (failure) {
        setError(messageOf(failure, "That could not be saved."));
      }
    });
  };

  const remove = async () => {
    if (!editing) return;
    const removed = await act(() => lumia.delete("schedules", editing.id), `Could not delete ${editing.name}.`);
    if (removed) {
      onDeleted();
      toast(`${editing.name} deleted`, { label: "Undo", run: () => act(() => lumia.create("schedules", schedulePayload(editing)), `Could not restore ${editing.name}.`) });
    }
  };

  return (
    <form className="lv-form ll-schedule-form" onSubmit={submit}>
      <label className="lv-field">
        Name
        <input className="lv-input" placeholder="Wake up" maxLength={100} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <div className="ll-segments ll-segments-wide" role="group" aria-label="Type">
        <button className={kind === "schedule" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={kind === "schedule"} onClick={() => setKind("schedule")}>
          <Clock size={15} />
          Schedule
        </button>
        <button className={kind === "alarm" ? "ll-segment ll-segment-active" : "ll-segment"} type="button" aria-pressed={kind === "alarm"} onClick={() => setKind("alarm")}>
          <AlarmClock size={15} />
          Alarm
        </button>
      </div>
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
          {offset ? `${Math.abs(offset)} min ${offset < 0 ? "before" : "after"} ${when}` : `At ${when}`}
          {preview ? ` · ${preview} today` : ""}
          <input type="range" min={MIN_OFFSET} max={MAX_OFFSET} step={5} value={offset} onChange={(event) => setOffset(Number(event.target.value))} />
        </label>
      )}
      {when !== "time" && !dashboard.location && <p className="lv-alert">Set your location above to schedule at sunrise or sunset.</p>}
      <label className="lv-field">
        Do
        <select className="lv-select" value={what} onChange={(event) => setWhat(event.target.value)}>
          <option value="on">Turn on</option>
          <option value="off">Turn off</option>
          <optgroup label="Play a scheme">
            {schemes.map(({ id, name: schemeName }) => (
              <option value={doKey("scene", id)} key={id}>
                Play {schemeName}
              </option>
            ))}
          </optgroup>
        </select>
      </label>
      <div className="lv-field">
        On
        <div className="ll-chips" role="group" aria-label="On">
          {places.map((option) => (
            <button className={target === option.key ? "ll-choice ll-choice-active" : "ll-choice"} type="button" aria-pressed={target === option.key} key={option.key} onClick={() => setTarget(option.key)}>
              {option.label.replace(/^(Room|Group) · /, "")}
            </button>
          ))}
        </div>
        {lights.length > 0 && (
          <select className="lv-select" aria-label="Or one light" value={lights.some((option) => option.key === target) ? target : ""} onChange={(event) => event.target.value && setTarget(event.target.value)}>
            <option value="">Or one light…</option>
            {lights.map((option) => (
              <option value={option.key} key={option.key}>
                {option.label.replace(/^Light · /, "")}
              </option>
            ))}
          </select>
        )}
      </div>
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
        {once ? (
          <input
            className="lv-input"
            type="date"
            aria-label="Date"
            value={runDate}
            min={runDate < todayIso() ? runDate : todayIso()}
            required
            onChange={(event) => setRunDate(event.target.value)}
          />
        ) : (
          <div className="ll-days" role="group" aria-label="Repeat on">
            {settings.weekday_names.map((label, day) => (
              <button className={days.includes(day) ? "ll-day-pick ll-day-pick-on" : "ll-day-pick"} type="button" aria-pressed={days.includes(day)} aria-label={label} title={label} key={label} onClick={() => toggleDay(day)}>
                {label.charAt(0)}
              </button>
            ))}
          </div>
        )}
      </div>
      {once && <p className="lv-caption">Runs once on this day, then switches itself off.</p>}
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <div className="ll-form-actions">
        <button className="lv-button lv-button-primary ll-grow" type="submit">
          <Save size={17} />
          {editing ? "Save changes" : "Save schedule"}
        </button>
        {editing && (
          <button className="lv-button" type="button" aria-label={`Delete ${editing.name}`} title="Delete" onClick={remove}>
            <Trash2 size={16} />
          </button>
        )}
      </div>
    </form>
  );
}

function ScheduleRow({ schedule, dashboard, settings, selected, onSelect }: TabProps & { schedule: Schedule; selected: boolean; onSelect: () => void }) {
  const act = useAct();
  const toast = useToast();
  const now = useNow();
  const options = targetOptions(dashboard);
  const target = (options.find((option) => option.key === targetKey(schedule.target_type, schedule.target_id))?.label ?? "Deleted target").replace(/^(Room|Group|Light) · /, "");
  const action =
    schedule.action === "scene" ? `Play ${dashboard.scenes.find(({ id }) => id === schedule.scene_id)?.name ?? "a deleted scheme"}` : `Turn ${schedule.action}`;
  const finished = isFinished(schedule);
  const active = schedule.enabled !== false && !finished;
  const run = nextRun(schedule, now);

  const setActive = (on: boolean) =>
    act(() => lumia.update("schedules", schedule.id, schedulePayload(schedule, { enabled: on })), `Could not ${on ? "resume" : "pause"} ${schedule.name}.`).then(
      (done) => done && toast(`${schedule.name} ${on ? "resumed" : "paused"}`),
    );

  return (
    <li className={`ll-schedule${active ? "" : " ll-schedule-paused"}${selected ? " ll-schedule-selected" : ""}`}>
      <button className="ll-schedule-select" type="button" aria-pressed={selected} onClick={onSelect}>
        <span className="ll-clock">
          {scheduleClock(schedule)}
          <small>{scheduleAnchor(schedule, Boolean(dashboard.location))}</small>
        </span>
        <span className="ll-schedule-main">
          <strong>
            <span className="ll-truncate" title={schedule.name}>
              {schedule.name}
            </span>
            {schedule.kind === "alarm" && <span className="ll-tag ll-tag-alarm">Alarm</span>}
            {finished ? <span className="ll-tag">Done</span> : schedule.enabled === false && <span className="ll-tag">Paused</span>}
          </strong>
          <span className="ll-schedule-what">
            <DoStrip dashboard={dashboard} schedule={schedule} />
            <span className="ll-truncate">
              {action} · {target}
            </span>
          </span>
          <span className="ll-now-label">{finished ? "Ran on its date. Edit it to set a new one." : run ? `Next ${run.label}` : active ? "No upcoming run" : "Paused"}</span>
        </span>
        <span className="ll-week" aria-label={scheduleDays(schedule, settings.weekday_names)}>
          {settings.weekday_names.map((label, day) => (
            <span className={!schedule.run_date && schedule.weekdays.includes(day) ? "ll-week-on" : undefined} aria-hidden="true" key={label}>
              {label.charAt(0)}
            </span>
          ))}
        </span>
      </button>
      <span className="ll-schedule-switch">
        <Toggle label={`${schedule.name} active`} hideLabel checked={active} disabled={finished} onChange={setActive} />
      </span>
    </li>
  );
}

export function SchedulesTab({ dashboard, settings }: TabProps) {
  const [selected, setSelected] = useState<number | "new">(() => dashboard.schedules[0]?.id ?? "new");
  const [locating, setLocating] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const sorted = [...dashboard.schedules].sort((a, b) => (minutesOf(scheduleClock(a)) ?? 1440) - (minutesOf(scheduleClock(b)) ?? 1440));
  const editing = selected === "new" ? undefined : dashboard.schedules.find((schedule) => schedule.id === selected);

  // On a phone the editor sits below the list, so bring it into view.
  const choose = (next: number | "new") => {
    setSelected(next);
    if (window.matchMedia("(max-width: 960px)").matches) window.setTimeout(() => panel.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
  };
  const afterSave = (name: string) => {
    if (selected === "new") {
      const created = dashboard.schedules.find((schedule) => schedule.name === name);
      if (created) setSelected(created.id);
    }
  };

  return (
    <>
      <Today dashboard={dashboard} onLocation={() => setLocating(true)} />
      <div className="ll-split">
        <section className="ll-split-main" aria-labelledby="schedules-title">
          <SectionHead title="Schedules and alarms" count={dashboard.schedules.length} id="schedules-title">
            <button className="lv-button lv-button-primary" type="button" onClick={() => choose("new")}>
              <Plus size={17} />
              New schedule
            </button>
          </SectionHead>
          {sorted.length ? (
            <ul className="ll-schedules">
              {sorted.map((schedule) => (
                <ScheduleRow schedule={schedule} dashboard={dashboard} settings={settings} selected={schedule.id === selected} onSelect={() => choose(schedule.id)} key={schedule.id} />
              ))}
            </ul>
          ) : (
            <p className="lv-alert">No schedules yet. A schedule turns lights on or off, or plays a scheme, at a time or with the sun.</p>
          )}
        </section>
        <aside className="ll-split-panel" ref={panel} aria-label={editing ? `Edit ${editing.name}` : "New schedule"}>
          <div className="ll-panel-head">
            <span className="ll-now-label">{editing ? (editing.kind === "alarm" ? "Editing alarm" : "Editing schedule") : "New schedule or alarm"}</span>
            <strong>{editing?.name ?? "Untitled"}</strong>
          </div>
          <ScheduleForm
            dashboard={dashboard}
            settings={settings}
            editing={editing}
            key={editing?.id ?? "new"}
            onSaved={afterSave}
            onDeleted={() => setSelected("new")}
          />
          <p className="lv-caption">Sunrise and sunset follow your location{dashboard.location ? `, ${dashboard.location.name}` : ""}. An alarm fades the lights up over its scheme's length.</p>
        </aside>
      </div>
      {locating && <LocationDialog dashboard={dashboard} onClose={() => setLocating(false)} />}
    </>
  );
}
