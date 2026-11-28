import { describe, expect, it } from "vitest";

import { animate, animatedScheme, comboOf, effectColor, effectLevel, leftToRight } from "./pc";

const press = (code: string, mods: Partial<Record<"ctrlKey" | "altKey" | "shiftKey" | "metaKey", boolean>> = {}) =>
  ({ code, ctrlKey: false, altKey: false, shiftKey: false, metaKey: false, ...mods });

describe("effects, as the backend plays them", () => {
  it("blinks half a cycle on, half off", () => {
    const blink = { type: "blink" as const, period_ms: 1000 };
    expect([0, 0.4, 0.6, 1.1].map((t) => effectLevel(blink, t))).toEqual([1, 1, 0, 1]);
  });

  it("glows down to a third, and a rainbow turns through the hues", () => {
    expect(effectColor({ type: "glow", period_ms: 1000 }, "#FF0000", 0.5)).toBe("#540000");
    expect(effectColor({ type: "rainbow", period_ms: 3000 }, "#000000", 1)).toBe("#00FF00");
  });

  it("chases: each listed key starts later than the one before", () => {
    const pattern = { background: "#000000", brightness: 100, keys: { Q: "#FFFFFF", W: "#FFFFFF" } };
    const frame = animate(pattern, [{ type: "blink", period_ms: 1000, stagger_ms: 500, keys: ["Q", "W"] }], 0.1, ["Q", "W", "E"]);
    expect(frame.keys).toEqual({ Q: "#FFFFFF", W: "#000000" });
  });

  it("orders keys left to right so a chase waves across the keyboard", () => {
    const leds = [{ key: "E", x: 30, y: 0 }, { key: "Q", x: 10, y: 0 }, { key: "W", x: 20, y: 0 }];
    expect(leftToRight(["E", "Q", "W", "Nope"], leds)).toEqual(["Q", "W", "E"]);
  });

  it("saves a moving pattern as a per-key scheme that plays until stopped", () => {
    const pattern = { background: "#000000", brightness: 80, keys: { Escape: "#FF0000" } };
    const scheme = animatedScheme("Esc", pattern, [{ type: "breathe", period_ms: 2000, keys: ["Escape"] }]);
    expect(scheme).toMatchObject({ kind: "keys", loops: true, steps: [{ hold_ms: 0, keys: { Escape: "#FF0000" }, effects: [{ type: "breathe" }] }] });
  });
});

describe("recording a hotkey", () => {
  it("names the keys as the bridge does", () => {
    expect(comboOf(press("Digit1", { ctrlKey: true, altKey: true }))).toBe("Ctrl+Alt+1");
    expect(comboOf(press("KeyG", { metaKey: true, shiftKey: true }))).toBe("Shift+Win+G");
    expect(comboOf(press("ArrowUp", { ctrlKey: true }))).toBe("Ctrl+Up");
    expect(comboOf(press("Numpad7", { altKey: true }))).toBe("Alt+Num7");
    expect(comboOf(press("F9"))).toBe("F9");
  });

  it("waits while only modifiers are down", () => {
    expect(comboOf(press("ControlLeft", { ctrlKey: true }))).toBeNull();
  });
});
