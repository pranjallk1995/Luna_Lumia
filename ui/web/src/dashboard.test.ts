import { describe, expect, it } from "vitest";

import type { Dashboard, Light, Schedule, Scheme, Transition } from "./api";
import {
  addableLights,
  curvePoints,
  filterSchemes,
  kelvinColor,
  lightColor,
  lightState,
  minutesOf,
  nextRun,
  schedulePayload,
  schemePayload,
  schemeSegments,
  isFinished,
  isValidName,
  mostCommon,
  scheduleAnchor,
  scheduleClock,
  scheduleDays,
  seconds,
  shifted,
  targetOptions,
  weekdaysLabel,
} from "./dashboard";
import { validationReason } from "./http";

const NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const light = (id: number) => ({ id, name: `L${id}` }) as Light;
const dashboard = {
  lights: [light(1), light(2), light(3)],
  rooms: [{ id: 7, name: "Den", kind: "room", light_ids: [1] }],
  groups: [{ id: 8, name: "Up", kind: "group", light_ids: [2] }],
} as Dashboard;

describe("targets and membership", () => {
  it("offers all lights, each light, and rooms and groups as groups", () => {
    const options = targetOptions(dashboard);
    expect(options[0]).toMatchObject({ label: "All lights", type: "all", id: null });
    expect(options.find((option) => option.label === "Room · Den")).toMatchObject({ type: "group", id: 7 });
  });

  it("keeps a light to one room but lets it join many groups", () => {
    expect(addableLights(dashboard, dashboard.rooms[0]).map(({ id }) => id)).toEqual([2, 3]);
    expect(addableLights(dashboard, dashboard.groups[0]).map(({ id }) => id)).toEqual([1, 3]);
  });
});

describe("wording", () => {
  it("names follow the backend's rule", () => {
    expect(isValidName("Bedroom lamp 2")).toBe(true);
    expect(isValidName("Lamp!")).toBe(false);
    expect(isValidName("   ")).toBe(false);
  });

  it("ignores empty values when finding the most common", () => {
    expect(mostCommon([null, 5, 5, 7], 1)).toBe(5);
    expect(mostCommon([null], 1)).toBe(1);
  });

  it("formats fades", () => {
    expect(seconds(1500)).toBe("1.5 s");
    expect(seconds(90000)).toBe("1 min 30 s");
    // Rounded: these printed as raw floats before.
    expect(seconds(160000)).toBe("2 min 40 s");
    expect(seconds(66520)).toBe("1 min 7 s");
    expect(seconds(35265)).toBe("35.3 s");
    expect(seconds(119700)).toBe("2 min");
    expect(curvePoints({ curve: "linear", duration_ms: 0 })).toBe("0,28 0,4 100,4");
  });

  it("reads validation failures", () => {
    expect(validationReason({ msg: "Value error, too low", loc: ["steps", 1, "brightness"] })).toBe("Step 2 brightness: too low");
  });
});

describe("schedules", () => {
  it("clamps a sun offset to the same day", () => {
    expect(shifted("06:30", -45)).toBe("05:45");
    expect(shifted("00:10", -30)).toBe("00:00");
    expect(shifted("23:50", 30)).toBe("23:59");
    expect(shifted(null, 5)).toBeNull();
  });

  it("names repeat days", () => {
    expect(weekdaysLabel([0, 1, 2, 3, 4, 5, 6], NAMES)).toBe("Every day");
    expect(weekdaysLabel([0, 1, 2, 3, 4], NAMES)).toBe("Weekdays");
    expect(weekdaysLabel([5, 6], NAMES)).toBe("Weekends");
    expect(weekdaysLabel([0, 2], NAMES)).toBe("Mon, Wed");
  });

  it("shows a one-time date with its weekday", () => {
    expect(scheduleDays({ run_date: "2026-11-02", weekdays: [] } as never, NAMES)).toBe("Mon, 2 Nov 2026");
  });

  it("explains a sun schedule that cannot run", () => {
    const sun = { time_mode: "sunrise", offset_minutes: -10, weekdays: [] } as never;
    expect(scheduleAnchor(sun, false)).toBe("Sunrise − 10 min · set a location");
    expect(scheduleAnchor(sun, true)).toBe("Sunrise − 10 min · no sunrise today");
    expect(scheduleClock(sun)).toBe("--:--");
  });

  it("knows a one-time schedule has run", () => {
    expect(isFinished({ run_date: "2026-01-01", last_run_date: "2026-01-01" })).toBe(true);
    expect(isFinished({ run_date: "2026-01-02", last_run_date: "2026-01-01" })).toBe(false);
    expect(isFinished({ run_date: null, last_run_date: "2026-01-01" })).toBe(false);
  });
});

describe("redesign helpers", () => {
  it("colors a light by its temperature, else its color, and knows offline", () => {
    expect(kelvinColor(6500)).toBe("#FFFEFA");
    expect(kelvinColor(2700)).toBe("#FFA757");
    expect(lightColor({ color: "#CF5BD8", color_temp: 2700 })).toBe("#FFA757");
    expect(lightColor({ color: "#CF5BD8", color_temp: null })).toBe("#CF5BD8");
    expect(lightState({ is_on: true, reachable: false })).toBe("offline");
    expect(lightState({ is_on: true, reachable: null })).toBe("on");
    expect(lightState({ is_on: false, reachable: true })).toBe("off");
  });

  const scheme = (id: number, name: string, extra: Partial<Scheme> = {}) =>
    ({ id, name, kind: "solid", is_preset: true, brightness: 50, color_temp: 2700, loops: false, steps: [], weather_slots: [], music_moods: [], ...extra }) as Scheme;
  const library = [
    scheme(1, "Reading"),
    scheme(2, "Weather · Rain day", { weather_slots: ["rain/day"] }),
    scheme(3, "Music · Calm", { music_moods: ["calm"] }),
    scheme(4, "Coffee", { is_preset: false }),
  ];

  it("filters and searches the library, yours first", () => {
    expect(filterSchemes(library, "all", "").map((item) => item.id)).toEqual([4, 3, 1, 2]);
    expect(filterSchemes(library, "builtin", "").map((item) => item.id)).toEqual([1]);
    expect(filterSchemes(library, "weather", "").map((item) => item.id)).toEqual([2]);
    expect(filterSchemes(library, "all", "co").map((item) => item.id)).toEqual([4]);
  });

  it("sizes sequence steps by hold plus fade", () => {
    const transitions = [{ id: 1, name: "Smooth", duration_ms: 1500, curve: "linear", is_preset: true }] as Transition[];
    const sequence = scheme(5, "Pulse", {
      kind: "sequence",
      steps: [
        { color: "#FF0000", brightness: 100, hold_ms: 500, transition_id: 1 },
        { color_temp: 2700, brightness: 0, hold_ms: 0, transition_id: null },
      ],
    });
    const segments = schemeSegments(sequence, transitions);
    expect(segments.map((segment) => segment.weight)).toEqual([2000, 1]);
    expect(segments[1].color).toBe("#FFA757");
    expect(segments[1].opacity).toBeCloseTo(0.35);
  });

  it("rebuilds what was deleted", () => {
    expect(schemePayload(scheme(6, "Night", { color: "#FF6B3D", color_temp: null }))).toEqual({ name: "Night", kind: "solid", brightness: 50, color: "#FF6B3D" });
    const schedule = { id: 9, name: "Wake", kind: "alarm", target_type: "all", action: "on", weekdays: [0, 1], time_mode: "time", run_time: "07:00:00", enabled: true } as Schedule;
    expect(schedulePayload(schedule, { enabled: false })).toMatchObject({ name: "Wake", enabled: false, target_id: null, scene_id: null, run_date: null });
  });

  it("finds the next run", () => {
    // Monday 2 November 2026, 20:14.
    const now = new Date(2026, 10, 2, 20, 14);
    const daily = { id: 1, name: "Sunrise", kind: "schedule", weekdays: [0, 1, 2, 3, 4, 5, 6], time_mode: "sunrise", today_time: "06:13", enabled: true } as Schedule;
    expect(nextRun(daily, now)).toEqual({ inMinutes: 599, label: "tomorrow at 06:13" });
    expect(nextRun({ ...daily, today_time: "21:00" }, now)?.label).toBe("today at 21:00");
    expect(nextRun({ ...daily, weekdays: [3] }, now)?.label).toBe("Thursday at 06:13");
    expect(nextRun({ ...daily, enabled: false }, now)).toBeNull();
    expect(minutesOf("17:52")).toBe(1072);
    expect(minutesOf("--:--")).toBeNull();
  });
});
