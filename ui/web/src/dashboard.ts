/** Pure lookups and wording over the dashboard's data. */

import type { Collection, Dashboard, Light, Schedule, Scheme, Target, Transition } from "./api";

export const rgb = (hex: string) =>
  [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16)).join(",");

/** The rotation that colors cards and light pills: text, fill, and edge. */
const PALETTE = [
  ["#fca5a5", "220,38,38", "248,113,113"],
  ["#fcd34d", "217,119,6", "251,191,36"],
  ["#93c5fd", "37,99,235", "96,165,250"],
  ["#6ee7b7", "5,150,105", "52,211,153"],
  ["#d8b4fe", "147,51,234", "192,132,252"],
  ["#67e8f9", "8,145,178", "34,211,238"],
];

export function accent(index: number) {
  const [text, fill, edge] = PALETTE[index % PALETTE.length];
  return { "--pill-accent": text, "--pill-fill": fill, "--pill-edge": edge } as React.CSSProperties;
}

export function imageStyle(url?: string | null): React.CSSProperties {
  return url ? { backgroundImage: `url("${url.replace(/"/g, "%22")}")` } : {};
}

export type TargetOption = Target & { label: string; key: string };

export const targetKey = (type: string, id?: number | null) => `${type}:${id ?? ""}`;

/** Every place a scheme or schedule can act on; rooms are groups to the backend. */
export function targetOptions({ lights, rooms, groups }: Dashboard): TargetOption[] {
  const option = (label: string, type: string, id: number | null) => ({ label, type, id, key: targetKey(type, id) });
  return [
    option("All lights", "all", null),
    ...lights.map((light) => option(`Light · ${light.name}`, "light", light.id)),
    ...rooms.map((room) => option(`Room · ${room.name}`, "group", room.id)),
    ...groups.map((group) => option(`Group · ${group.name}`, "group", group.id)),
  ];
}

export function roomsByLight({ lights, rooms }: Dashboard): Record<number, string[]> {
  const names: Record<number, string[]> = Object.fromEntries(lights.map((light) => [light.id, []]));
  for (const room of rooms) {
    for (const id of room.light_ids) names[id]?.push(room.name);
  }
  return names;
}

/** Lights not yet in the collection; rooms also exclude lights in other rooms. */
export function addableLights(dashboard: Dashboard, collection: Collection): Light[] {
  const rooms = roomsByLight(dashboard);
  return dashboard.lights.filter(
    (light) => !collection.light_ids.includes(light.id) && (collection.kind === "group" || !rooms[light.id]?.length),
  );
}

export const isValidName = (value: string) => /^[\p{L}\p{N} ]+$/u.test(value.trim());

export function mostCommon<T>(values: (T | null | undefined)[], fallback: T): T {
  const counts = new Map<T, number>();
  for (const value of values) if (value) counts.set(value, (counts.get(value) ?? 0) + 1);
  let best = fallback;
  let most = 0;
  for (const [value, count] of counts) {
    if (count > most) [best, most] = [value, count];
  }
  return best;
}

export function seconds(milliseconds: number): string {
  const value = milliseconds / 1000;
  return value < 60 ? `${value} s` : `${value / 60} min`;
}

export function schemeDetails(scheme: Scheme): string {
  if (scheme.kind === "solid") {
    return `${scheme.color_temp ? `${scheme.color_temp} K` : scheme.color} · ${scheme.brightness}%`;
  }
  return `${scheme.steps.length} steps · ${seconds(scheme.cycle_ms ?? 0)} · ${scheme.loops ? "loops" : "plays once"}`;
}

export function schemePreview(scheme: Scheme): string {
  const colors = scheme.preview_colors?.length ? scheme.preview_colors : ["#444444"];
  return colors.length === 1 ? colors[0] : `linear-gradient(90deg,${colors.join(",")})`;
}

export function temperatureSchemes(schemes: Scheme[], names: string[]): Scheme[] {
  const builtIn = new Map(
    schemes.filter((scheme) => scheme.is_preset && scheme.kind === "solid" && scheme.color_temp).map((scheme) => [scheme.name, scheme]),
  );
  return names.flatMap((name) => builtIn.get(name) ?? []);
}

/** How a fade progresses, as polyline points in a 100 x 30 box; a 0 s fade is a straight jump. */
export function curvePoints({ curve, duration_ms }: Pick<Transition, "curve" | "duration_ms">): string {
  if (duration_ms === 0) return "0,28 0,4 100,4";
  const eases: Record<string, (t: number) => number> = {
    linear: (t) => t,
    "ease-in": (t) => t * t,
    "ease-out": (t) => 1 - (1 - t) ** 2,
    "ease-in-out": (t) => t * t * (3 - 2 * t),
  };
  const ease = eases[curve] ?? eases.linear;
  return Array.from({ length: 21 }, (_, i) => `${i * 5},${(28 - ease(i / 20) * 24).toFixed(1)}`).join(" ");
}

// Schedules

export const WHEN = { time: "At a time", sunrise: "Sunrise", sunset: "Sunset" } as const;

export function offsetLabel(minutes: number): string {
  return minutes === 0 ? "" : ` ${minutes > 0 ? "+" : "−"} ${Math.abs(minutes)} min`;
}

/** ``hhmm`` moved by ``minutes``, clamped to the same day, for the form's preview. */
export function shifted(hhmm: string | null | undefined, minutes: number): string | null {
  if (!hhmm) return null;
  const [hours, mins] = hhmm.split(":").map(Number);
  const total = hours * 60 + mins + minutes;
  if (total < 0) return "00:00";
  if (total >= 24 * 60) return "23:59";
  return `${String(Math.floor(total / 60)).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

export const scheduleClock = (schedule: Schedule) =>
  (schedule.time_mode ?? "time") === "time" ? (schedule.run_time ?? "").slice(0, 5) : (schedule.today_time ?? "--:--");

export function scheduleAnchor(schedule: Schedule, hasLocation: boolean): string {
  const mode = schedule.time_mode ?? "time";
  if (mode === "time") return WHEN[mode];
  const label = `${WHEN[mode]}${offsetLabel(schedule.offset_minutes ?? 0)}`;
  if (!hasLocation) return `${label} · set a location`;
  const day = schedule.run_date ? "that day" : "today";
  return schedule.today_time ? label : `${label} · no ${mode} ${day}`;
}

/** A one-time schedule that has already run. */
export const isFinished = ({ run_date, last_run_date }: Pick<Schedule, "run_date" | "last_run_date">) =>
  Boolean(run_date && last_run_date && last_run_date >= run_date);

export function weekdaysLabel(weekdays: number[], names: string[]): string {
  if (weekdays.length === 7) return "Every day";
  if (weekdays.join() === "0,1,2,3,4") return "Weekdays";
  if (weekdays.join() === "5,6") return "Weekends";
  return weekdays.map((day) => names[day]).join(", ");
}

/** Its repeat days, or the date of a one-time schedule. */
export function scheduleDays(schedule: Schedule, names: string[]): string {
  if (!schedule.run_date) return weekdaysLabel(schedule.weekdays, names);
  const day = new Date(`${schedule.run_date}T00:00:00Z`);
  const month = day.toLocaleDateString("en-GB", { month: "short", timeZone: "UTC" });
  return `${names[(day.getUTCDay() + 6) % 7]}, ${day.getUTCDate()} ${month} ${day.getUTCFullYear()}`;
}

export const todayIso = () => {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
};
