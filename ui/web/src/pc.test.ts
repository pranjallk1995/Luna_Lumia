import { describe, expect, it } from "vitest";

import { isKeyboard, keyLabel, paint, paintPayload, patternFromScheme, rainbow, schemeFromPattern, shown, viewBox, type Pattern } from "./pc";
import type { Scheme } from "./api";

const blank: Pattern = { background: "#000000", brightness: 80, keys: {} };
const keys = [{ key: "Escape", x: 41.5, y: 37.9 }, { key: "W", x: 66.3, y: 58.6 }, { key: "Space", x: 104.6, y: 88.1 }];
const strip = Array.from({ length: 8 }, (_, n) => ({ key: `LED ${n + 1}`, x: n + 1, y: 0 }));

describe("PC tab", () => {
  it("labels keys as they are printed", () => {
    expect([keyLabel("Escape"), keyLabel("Keypad7"), keyLabel("UpArrow"), keyLabel("W"), keyLabel("LED 12")]).toEqual(["Esc", "7", "↑", "W", "12"]);
  });

  it("tells a keyboard from a strip and frames them", () => {
    expect(isKeyboard(strip)).toBe(false);
    expect(isKeyboard(Array.from({ length: 30 }, (_, n) => ({ key: `K${n}`, x: n * 10, y: (n % 3) * 10 })))).toBe(true);
    expect(viewBox(strip, false)).toBe("0 -1 9 2");
  });

  it("paints keys, and painting the background takes them out", () => {
    const red = paint(blank, ["W", "Space"], "#ff0000");
    expect(red.keys).toEqual({ W: "#FF0000", Space: "#FF0000" });
    expect(shown(red, "Escape")).toBe("#000000");
    expect(paint(red, ["W"], "#000000").keys).toEqual({ Space: "#FF0000" });
    expect(paintPayload(red)).toEqual({ color: "#000000", brightness: 80, keys: { W: "#FF0000", Space: "#FF0000" } });
  });

  it("saves a pattern as a still per-key scheme and opens it again", () => {
    const saved = schemeFromPattern("Gaming", paint(blank, ["W"], "#ff0000"));
    expect(saved).toMatchObject({ name: "Gaming", kind: "keys", steps: [{ color: "#000000", brightness: 80, keys: { W: "#FF0000" } }] });
    expect(patternFromScheme({ ...saved, id: 1, is_preset: false, brightness: 0 } as unknown as Scheme)).toEqual(paint(blank, ["W"], "#ff0000"));
    expect(patternFromScheme({ id: 2, kind: "solid", steps: [] } as unknown as Scheme)).toBeNull();
  });

  it("spreads a rainbow along the keys from red", () => {
    const colors = rainbow(blank, keys).keys;
    expect(colors.Escape).toBe("#FF0000");
    expect(new Set(Object.values(colors)).size).toBe(3);
  });
});
