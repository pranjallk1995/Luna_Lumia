import { describe, expect, it } from "vitest";

import type { Dashboard, Light } from "./api";
import {
  addableLights,
  curvePoints,
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
    expect(seconds(90000)).toBe("1.5 min");
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
