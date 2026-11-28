/** Pure lookups and wording over the dashboard's data. */

import type { Collection, Dashboard, Discovered, Light, MovedPcLights, Schedule, Scheme, Step, Target, Transition } from "./api";

export const rgb = (hex: string) =>
  [1, 3, 5].map((start) => parseInt(hex.slice(start, start + 2), 16)).join(",");

/** A white point in kelvin as an sRGB hex, after Tanner Helland's fit; close enough for a swatch. */
export function kelvinColor(kelvin: number): string {
  const t = kelvin / 100;
  const red = t <= 66 ? 255 : 329.698727446 * (t - 60) ** -0.1332047592;
  const green = t <= 66 ? 99.4708025861 * Math.log(t) - 161.1195681661 : 288.1221695283 * (t - 60) ** -0.0755148492;
  const blue = t >= 66 ? 255 : t <= 19 ? 0 : 138.5177312231 * Math.log(t - 10) - 305.0447927307;
  return `#${[red, green, blue].map((value) => Math.round(Math.min(255, Math.max(0, value))).toString(16).padStart(2, "0")).join("")}`.toUpperCase();
}

/** The color a light shows. Its temperature is empty while it shows a color, and its last color is kept while it shows a temperature. */
export const lightColor = (light: Pick<Light, "color" | "color_temp">) => (light.color_temp ? kelvinColor(light.color_temp) : light.color || "#FFFFFF");

/** The color on a light this moment: a playing scheme's current frame, else its saved state. */
export const shownColor = ({ live }: Pick<Dashboard, "live">, light: Pick<Light, "id" | "color" | "color_temp">) => {
  const frame = live[light.id];
  return lightColor(frame ? { color: frame.color ?? light.color, color_temp: frame.color_temp ?? null } : light);
};

export const stepColor =(step: Pick<Step, "color" | "color_temp">) => step.color || kelvinColor(step.color_temp || 4000);

/** On, off, or offline: the one state that decides how a light is drawn and whether it can be changed. */
export const lightState = (light: Pick<Light, "is_on" | "reachable">) => (light.reachable === false ? "offline" : light.is_on ? "on" : "off");

/** A light's room, if it has one. */
export const roomOf = ({ rooms }: Pick<Dashboard, "rooms">, lightId: number) => rooms.find((room) => room.light_ids.includes(lightId));

/** Whether a card shows a picture of its own, not none or one borrowed from the room-image catalog. */
export const hasOwnPicture = ({ room_images }: Pick<Dashboard, "room_images">, url?: string | null) =>
  Boolean(url) && !room_images.some((image) => image.image_url === url);

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

/** "1.5 s", "35.3 s", "2 min 40 s": rounded, so a 160 s sequence never reads 2.6666666666666665 min. */
export function seconds(milliseconds: number): string {
  const value = milliseconds / 1000;
  if (value < 60) return `${Number(value.toFixed(1))} s`;
  let minutes = Math.floor(value / 60);
  let rest = Math.round(value - minutes * 60);
  if (rest === 60) [minutes, rest] = [minutes + 1, 0];
  return rest ? `${minutes} min ${rest} s` : `${minutes} min`;
}

export function schemeDetails(scheme: Scheme): string {
  if (scheme.kind === "solid") {
    return `${scheme.color_temp ? `${scheme.color_temp} K` : scheme.color} · ${scheme.brightness}%`;
  }
  if (scheme.kind === "keys") {
    const keys = `${scheme.keys_colored ?? 0} ${scheme.keys_colored === 1 ? "key" : "keys"}`;
    if (scheme.steps.length === 1) return `${keys} · ${scheme.steps[0].brightness}%`;
    return `${keys} · ${scheme.steps.length} steps · ${seconds(scheme.cycle_ms ?? 0)} · ${scheme.loops ? "loops" : "plays once"}`;
  }
  return `${scheme.steps.length} steps · ${seconds(scheme.cycle_ms ?? 0)} · ${scheme.loops ? "loops" : "plays once"}`;
}

/** A scheme as segments sized by time: each step's hold plus its fade in. */
export function schemeSegments(scheme: Scheme, transitions: Transition[]) {
  const shade = (brightness: number | null | undefined) => 0.35 + ((brightness ?? 100) / 100) * 0.65;
  if (scheme.kind === "solid") return [{ color: stepColor(scheme), weight: 1, opacity: shade(scheme.brightness) }];
  const fade = (id?: number | null) => transitions.find((item) => item.id === id)?.duration_ms ?? 0;
  return scheme.steps.map((step) => ({ color: stepColor(step), weight: Math.max((step.hold_ms ?? 0) + fade(step.transition_id), 1), opacity: shade(step.brightness) }));
}

export type SchemeFilter = "all" | "mine" | "builtin" | "weather" | "music";

export const SCHEME_FILTERS: [SchemeFilter, string, (scheme: Scheme) => boolean][] = [
  ["all", "All", () => true],
  ["mine", "Yours", (scheme) => !scheme.is_preset],
  ["builtin", "Built-in", (scheme) => scheme.is_preset && !scheme.weather_slots?.length && !scheme.music_moods?.length],
  ["weather", "Weather", (scheme) => Boolean(scheme.weather_slots?.length)],
  ["music", "Music", (scheme) => Boolean(scheme.music_moods?.length)],
];

/** The library for one filter and search, your own schemes first. */
export function filterSchemes(schemes: Scheme[], filter: SchemeFilter, search: string): Scheme[] {
  const test = SCHEME_FILTERS.find(([id]) => id === filter)![2];
  const query = search.trim().toLowerCase();
  return schemes
    .filter((scheme) => test(scheme) && (!query || scheme.name.toLowerCase().includes(query)))
    .sort((a, b) => Number(a.is_preset) - Number(b.is_preset) || a.name.localeCompare(b.name));
}

/** What saving a scheme sends, so a deleted one can be brought back. */
export function schemePayload(scheme: Scheme) {
  if (scheme.kind === "solid") {
    return { name: scheme.name, kind: "solid", brightness: scheme.brightness, ...(scheme.color ? { color: scheme.color } : { color_temp: scheme.color_temp }) };
  }
  return {
    name: scheme.name,
    kind: scheme.kind,
    loops: scheme.loops,
    steps: scheme.steps.map(({ color, color_temp, brightness, hold_ms, transition_id, keys }) => ({
      ...(color ? { color } : { color_temp }),
      brightness,
      hold_ms: hold_ms ?? 0,
      transition_id: transition_id ?? null,
      ...(keys ? { keys } : {}),
    })),
  };
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

/** What saving a schedule sends; used to pause or resume it, and to bring a deleted one back. */
export const schedulePayload = (schedule: Schedule, change: Partial<Schedule> = {}) => {
  const merged = { ...schedule, ...change };
  return {
    name: merged.name,
    kind: merged.kind,
    target_type: merged.target_type,
    target_id: merged.target_id ?? null,
    action: merged.action,
    scene_id: merged.scene_id ?? null,
    time_mode: merged.time_mode ?? "time",
    run_time: merged.run_time ?? null,
    offset_minutes: merged.offset_minutes ?? 0,
    weekdays: merged.weekdays,
    run_date: merged.run_date ?? null,
    enabled: merged.enabled ?? true,
  };
};

/** Minutes since midnight for "HH:MM", or null. */
export function minutesOf(hhmm?: string | null): number | null {
  if (!hhmm || !/^\d{1,2}:\d{2}/.test(hhmm)) return null;
  const [hours, minutes] = hhmm.split(":").map(Number);
  return hours * 60 + minutes;
}

/** Whether a schedule runs on this weekday (0 is Monday) and date. */
const runsOn = (schedule: Schedule, weekday: number, date: string) =>
  schedule.run_date ? schedule.run_date === date : schedule.weekdays.includes(weekday);

/**
 * When an active schedule next runs, from ``now``, looking a week ahead. Sun times are
 * today's, which is close enough for a label that says "tomorrow at 06:13".
 */
export function nextRun(schedule: Schedule, now: Date): { inMinutes: number; label: string } | null {
  if (schedule.enabled === false || isFinished(schedule)) return null;
  const at = minutesOf(scheduleClock(schedule));
  if (at === null) return null;
  const current = now.getHours() * 60 + now.getMinutes();
  for (let ahead = 0; ahead < 8; ahead += 1) {
    const day = new Date(now.getFullYear(), now.getMonth(), now.getDate() + ahead);
    const date = `${day.getFullYear()}-${String(day.getMonth() + 1).padStart(2, "0")}-${String(day.getDate()).padStart(2, "0")}`;
    if (!runsOn(schedule, (day.getDay() + 6) % 7, date) || (ahead === 0 && at <= current)) continue;
    const when = ahead === 0 ? "today" : ahead === 1 ? "tomorrow" : day.toLocaleDateString("en-GB", { weekday: "long" });
    return { inMinutes: ahead * 1440 + at - current, label: `${when} at ${scheduleClock(schedule)}` };
  }
  return null;
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

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** What "Find moved lights" says: which lights it followed to new addresses, and which it could not find. */
export function movedSummary(dashboard: Dashboard, bulbs: Discovered[], pcs: MovedPcLights | null): string {
  const byIp = new Map(dashboard.lights.filter((light) => !light.device).map((light) => [light.ip_address, light.name]));
  const movedBulbs = bulbs.filter((bulb) => bulb.moved_from).map((bulb) => byIp.get(bulb.moved_from!) ?? bulb.suggested_name);
  const moved = [...movedBulbs, ...(pcs?.moved ?? []).map((light) => light.name)];
  // By MAC, since another bulb may have taken a silent one's address.
  const found = new Set(bulbs.map((bulb) => bulb.mac_address?.toUpperCase()));
  const silentBulbs = dashboard.lights.filter((light) => light.mac_address && !light.device && !found.has(light.mac_address.toUpperCase()));
  const parts = [moved.length ? `Moved ${plural(moved.length, "light")} to new addresses: ${moved.join(", ")}.` : "No light had moved."];
  if (silentBulbs.length) parts.push(`${silentBulbs.map((light) => light.name).join(", ")} did not answer: switched off at the wall?`);
  if (pcs?.not_found.length)
    parts.push(`${pcs.not_found.join(", ")} not found on ${pcs.scanned.join(", ")}: is the PC on, with OpenRGB's server and the iCUE bridge running?`);
  if (pcs?.ambiguous.length) parts.push(`${pcs.ambiguous.map((item) => item.name).join(", ")} answered on several PCs, so they stayed put.`);
  return parts.join(" ");
}

// Home

/** A room tile, or a light in no room, on the Home tab; ``key`` is its target key. */
export type Tile = { key: string; target: Target; name: string; lights: Light[] };

export const parseTargetKey = (key: string): Target => {
  const [type, id] = key.split(":");
  return { type, id: id ? Number(id) : null };
};

/** Every room, then each light that is in no room, so no light goes missing from Home. */
export function homeTiles({ lights, rooms }: Pick<Dashboard, "lights" | "rooms">): Tile[] {
  const byId = new Map(lights.map((light) => [light.id, light]));
  const roomed = new Set(rooms.flatMap((room) => room.light_ids));
  return [
    ...rooms.map((room) => ({
      key: targetKey("group", room.id),
      target: { type: "group", id: room.id },
      name: room.name,
      lights: room.light_ids.flatMap((id) => byId.get(id) ?? []),
    })),
    ...lights
      .filter((light) => !roomed.has(light.id))
      .map((light) => ({ key: targetKey("light", light.id), target: { type: "light", id: light.id }, name: light.name, lights: [light] })),
  ];
}

/** The lights a selection covers: rooms and groups by their members, lights by themselves. */
export function selectedLights({ lights, rooms, groups }: Pick<Dashboard, "lights" | "rooms" | "groups">, keys: string[]): Light[] {
  const ids = new Set<number>();
  for (const key of keys) {
    const { type, id } = parseTargetKey(key);
    if (type === "light" && id !== null) ids.add(id);
    else [...rooms, ...groups].find((collection) => collection.id === id)?.light_ids.forEach((member) => ids.add(member));
  }
  return lights.filter((light) => ids.has(light.id));
}

/** A light's brightness this moment: a playing scheme's frame, else its saved state. */
export const shownBrightness = ({ live }: Pick<Dashboard, "live">, light: Pick<Light, "id" | "brightness">) =>
  live[light.id]?.brightness ?? light.brightness;

/** Relative luminance of a "#RRGGBB" color, 0 for black to 1 for white. */
export const luminance = (hex: string) => {
  const [r, g, b] = rgb(hex).split(",").map((value) => Number(value) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};

/** A tile's light: each lit light glows in its color, stronger the brighter it is; none when all are off. */
export function tileGlow(dashboard: Pick<Dashboard, "live">, lights: Light[]): string | undefined {
  const lit = lights.filter((light) => lightState(light) === "on").slice(0, 4);
  if (!lit.length) return undefined;
  return lit
    .map((light, index) => {
      // A light showing black (a keyboard between per-key frames) still reads as on: a faint white glow.
      const shown = shownColor(dashboard, light);
      const tint = luminance(shown) < 0.04 ? "255,255,255" : rgb(shown);
      const alpha = (0.2 + 0.5 * (shownBrightness(dashboard, light) / 100)).toFixed(2);
      const x = Math.round(((index + 0.5) / lit.length) * 100);
      return `radial-gradient(120% 95% at ${x}% 0%, rgba(${tint},${alpha}), rgba(${tint},0.04) 72%)`;
    })
    .join(", ");
}

/** "On · 62%", "2 of 3 on · 80% · 1 offline", "Off", or "Offline". */
export function tileStatus(dashboard: Pick<Dashboard, "live">, lights: Light[]): string {
  if (!lights.length) return "No lights";
  const on = lights.filter((light) => lightState(light) === "on");
  const offline = lights.filter((light) => lightState(light) === "offline").length;
  const parts = on.length
    ? [lights.length > 1 ? `${on.length} of ${lights.length} on` : "On", `${mostCommon(on.map((light) => shownBrightness(dashboard, light)), 100)}%`]
    : [offline === lights.length ? "Offline" : "Off"];
  if (offline && offline < lights.length) parts.push(`${offline} offline`);
  return parts.join(" · ");
}

/** The scheme playing on most of these lights, if any. */
export function playingScheme({ playing, scenes }: Pick<Dashboard, "playing" | "scenes">, lights: Pick<Light, "id">[]): Scheme | undefined {
  const id = mostCommon(lights.map((light) => playing[light.id]), 0);
  return scenes.find((scheme) => scheme.id === id);
}

/** Each playing scheme with where it plays: its rooms, and lights in no room by name. */
export function playingNow(dashboard: Pick<Dashboard, "playing" | "scenes" | "lights" | "rooms">): { scheme?: Scheme; places: string[]; lights: number }[] {
  const byScheme = new Map<number, number[]>();
  for (const [lightId, schemeId] of Object.entries(dashboard.playing)) byScheme.set(schemeId, [...(byScheme.get(schemeId) ?? []), Number(lightId)]);
  return [...byScheme].map(([schemeId, ids]) => {
    const places = ids.map((id) => roomOf(dashboard, id)?.name ?? dashboard.lights.find((light) => light.id === id)?.name ?? "a light");
    return { scheme: dashboard.scenes.find((scheme) => scheme.id === schemeId), places: [...new Set(places)], lights: ids.length };
  });
}

/** The schedule that runs next, within a week, and what it acts on. */
export function upcomingSchedule(dashboard: Pick<Dashboard, "schedules" | "lights" | "rooms" | "groups">, now: Date) {
  const runs = dashboard.schedules
    .map((schedule) => ({ schedule, run: nextRun(schedule, now) }))
    .filter((item): item is { schedule: Schedule; run: { inMinutes: number; label: string } } => item.run !== null)
    .sort((a, b) => a.run.inMinutes - b.run.inMinutes);
  if (!runs.length) return null;
  const { schedule, run } = runs[0];
  const id = schedule.target_id;
  const where =
    schedule.target_type === "light"
      ? dashboard.lights.find((light) => light.id === id)?.name
      : schedule.target_type === "group"
        ? [...dashboard.rooms, ...dashboard.groups].find((collection) => collection.id === id)?.name
        : schedule.target_type === "on"
          ? "Lights that are on"
          : "All lights";
  return { schedule, label: run.label, where: where ?? "A deleted target", later: runs.length - 1 };
}

/** Schemes for everyday use on Home, the ones playing here first, then your own: weather, music and per-key ones stay on Schemes. */
export function everydaySchemes(schemes: Scheme[], playingIds: number[]): Scheme[] {
  return schemes
    .filter((scheme) => scheme.kind !== "keys" && !scheme.weather_slots?.length && !scheme.music_moods?.length)
    .sort(
      (a, b) =>
        Number(playingIds.includes(b.id)) - Number(playingIds.includes(a.id)) ||
        Number(a.is_preset) - Number(b.is_preset) ||
        a.name.localeCompare(b.name),
    );
}
