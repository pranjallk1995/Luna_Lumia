/** The PC tab: keyboard keys and case LEDs, each painted its own color. */

import type { Effect, EffectType, Light, Scheme } from "./api";

/** One key of a keyboard, or one LED of a case part, with its place on the device. */
export type Led = { key: string; x: number; y: number };

/** A PC light's keys or LEDs, and (keyboards) the named groups it has. */
export type LightLeds = { light_id: number; name: string; keys: Led[]; groups: Record<string, string[]> };

/** What the editor holds: each painted key's color; unpainted keys show the background. */
export type Pattern = { background: string; brightness: number; keys: Record<string, string> };

export const isPcLight = (light: Light) => light.protocol === "icue" || light.protocol === "openrgb";

/** A keyboard draws as keys by position; a mouse or a case part as a row of its LEDs. */
export const isKeyboard = (leds: Led[]) => leds.some((led) => led.y > 0) && leds.length > 20;

const SHORT: Record<string, string> = {
  Escape: "Esc", GraveAccentAndTilde: "`", MinusAndUnderscore: "-", EqualsAndPlus: "=", Backspace: "⌫",
  BracketLeft: "[", BracketRight: "]", Backslash: "\\", NonUsBackslash: "\\", NonUsTilde: "#", CapsLock: "Caps",
  SemicolonAndColon: ";", ApostropheAndDoubleQuote: "'", Enter: "↵", CommaAndLessThan: ",",
  PeriodAndBiggerThan: ".", SlashAndQuestionMark: "/", LeftShift: "Shift", RightShift: "Shift", LeftCtrl: "Ctrl",
  RightCtrl: "Ctrl", LeftAlt: "Alt", RightAlt: "Alt", LeftGui: "Win", RightGui: "Win", Application: "Menu",
  Space: "Space", PrintScreen: "PrtSc", ScrollLock: "ScrLk", PauseBreak: "Pause", Insert: "Ins", Delete: "Del",
  PageUp: "PgUp", PageDown: "PgDn", UpArrow: "↑", DownArrow: "↓", LeftArrow: "←", RightArrow: "→",
  NumLock: "Num", KeypadSlash: "/", KeypadAsterisk: "*", KeypadMinus: "-", KeypadPlus: "+", KeypadEnter: "↵",
  KeypadPeriodAndDelete: ".", Mute: "🔇", VolumeUp: "🔊", VolumeDown: "🔉", PlayPause: "⏯", Stop: "⏹",
  ScanPreviousTrack: "⏮", ScanNextTrack: "⏭", Brightness: "☼", WinLock: "🔒", LedProgramming: "LED",
};

/** An LED iCUE gives no key name ("Keyboard 3": a logo or light bar), drawn as a plain key. */
const unnamed = (key: string) => /^Keyboard \d+$/.test(key);

/** The label printed on a key: "Esc" for Escape, "7" for Keypad7, "↑" for UpArrow. */
export function keyLabel(name: string): string {
  if (SHORT[name]) return SHORT[name];
  if (/^Keypad\d$/.test(name)) return name.slice(-1);
  if (/^LED \d+$/.test(name)) return name.slice(4);
  if (unnamed(name)) return "";
  return name.length > 4 ? name.slice(0, 4) : name;
}

/** A key or LED as drawn: its center, and its width and height in the device's layout units. */
export type KeyRect = Led & { w: number; h: number };

/** Key widths and heights in key units (1 = a letter key), as on a full-size keyboard. */
const WIDE: Record<string, [number, number]> = {
  Backspace: [2, 1], Tab: [1.5, 1], Backslash: [1.5, 1], CapsLock: [1.75, 1], Enter: [2.25, 1],
  LeftShift: [2.25, 1], RightShift: [2.75, 1], LeftCtrl: [1.25, 1], RightCtrl: [1.25, 1], LeftGui: [1.25, 1],
  RightGui: [1.25, 1], LeftAlt: [1.25, 1], RightAlt: [1.25, 1], Application: [1.25, 1], Fn: [1.25, 1],
  Space: [6.25, 1], Keypad0: [2, 1], KeypadPlus: [1, 2], KeypadEnter: [1, 2],
};
const GAP = 0.14;

/** The distance between two neighboring keys' centers: a key unit in the device's layout units. */
export function keyUnit(leds: Led[]): number {
  const at = (key: string) => leds.find((led) => led.key === key);
  const [q, w] = [at("Q"), at("W")];
  if (q && w && w.x > q.x) return w.x - q.x;
  const gaps = leds
    .map((led) => Math.min(...leds.filter((other) => other !== led && Math.abs(other.y - led.y) < 1).map((other) => Math.abs(other.x - led.x))))
    .filter((gap) => Number.isFinite(gap) && gap > 0)
    .sort((a, b) => a - b);
  return gaps.length ? gaps[Math.floor(gaps.length / 2)] : 10;
}

/**
 * Each key drawn as on the keyboard: Space, Shift, and Enter wide, keypad + and Enter tall, each shrunk
 * only as far as its neighbors need. Unnamed LEDs sitting on top of another (a logo's) are left out.
 */
export function keyRects(leds: Led[]): KeyRect[] {
  const u = keyUnit(leds);
  const crowded = (led: Led) =>
    unnamed(led.key) && leds.some((other) => other !== led && Math.hypot(other.x - led.x, other.y - led.y) < u * 0.75);
  const shown = leds.filter((led) => !crowded(led));
  const half = new Map(shown.map((led) => {
    const [w, h] = WIDE[led.key] ?? [1, 1];
    return [led.key, { w: ((w - GAP) * u) / 2, h: ((h - GAP) * u) / 2 }];
  }));
  const keyHalf = ((1 - GAP) * u) / 2;
  const fitted = new Map([...half].map(([key, size]) => [key, { ...size }]));
  // Two keys side by side (or one above the other) share the room between their centers; the wider gives way first.
  for (const [i, a] of shown.entries()) {
    for (const b of shown.slice(i + 1)) {
      const [dx, dy] = [Math.abs(a.x - b.x), Math.abs(a.y - b.y)];
      const axis = dy < u / 2 && dx >= dy ? "w" : dx < u / 2 && dy > dx ? "h" : null;
      if (!axis) continue;
      const [sa, sb] = [half.get(a.key)![axis], half.get(b.key)![axis]];
      const room = (axis === "w" ? dx : dy) - GAP * u;
      if (sa + sb <= room) continue;
      let [na, nb] = [sa, sb];
      let excess = sa + sb - room;
      const give = (size: number) => { const cut = Math.min(excess, Math.max(0, size - keyHalf)); excess -= cut; return size - cut; };
      if (na >= nb) { na = give(na); nb = give(nb); } else { nb = give(nb); na = give(na); }
      if (excess > 0) { na -= excess / 2; nb -= excess / 2; }
      fitted.get(a.key)![axis] = Math.min(fitted.get(a.key)![axis], na);
      fitted.get(b.key)![axis] = Math.min(fitted.get(b.key)![axis], nb);
    }
  }
  return shown.map((led) => {
    const size = fitted.get(led.key)!;
    return { ...led, w: Math.max(u * 0.3, size.w * 2), h: Math.max(u * 0.3, size.h * 2) };
  });
}

/** The SVG view box that holds every key (by its drawn size) or LED, with a little room around. */
export function viewBox(leds: Led[], keyboard: boolean): string {
  if (!leds.length) return "0 0 10 10";
  const rects: KeyRect[] = keyboard ? keyRects(leds) : leds.map((led) => ({ ...led, w: 1, h: 1 }));
  const pad = keyboard ? keyUnit(leds) * 0.15 : 0.5;
  const left = Math.min(...rects.map((r) => r.x - r.w / 2)) - pad;
  const top = Math.min(...rects.map((r) => r.y - r.h / 2)) - pad;
  const right = Math.max(...rects.map((r) => r.x + r.w / 2)) + pad;
  const bottom = Math.max(...rects.map((r) => r.y + r.h / 2)) + pad;
  return `${round(left)} ${round(top)} ${round(right - left)} ${round(bottom - top)}`;
}

const round = (value: number) => Math.round(value * 100) / 100;

/** What a key shows: its own color, or the background. */
export const shown = (pattern: Pattern, key: string) => pattern.keys[key] ?? pattern.background;

/** Paint keys one color; painting a key the background color takes it out of the pattern. */
export function paint(pattern: Pattern, keys: string[], color: string): Pattern {
  const next = { ...pattern.keys };
  for (const key of keys) {
    if (color.toUpperCase() === pattern.background.toUpperCase()) delete next[key];
    else next[key] = color.toUpperCase();
  }
  return { ...pattern, keys: next };
}

/** What the backend takes to show a pattern now. */
export const paintPayload = (pattern: Pattern) => ({ color: pattern.background, brightness: pattern.brightness, keys: pattern.keys });

/** A pattern saved as a still per-key scheme, to apply again, schedule, or animate later. */
export const schemeFromPattern = (name: string, pattern: Pattern) => ({
  name,
  kind: "keys",
  loops: false,
  steps: [{ color: pattern.background, brightness: pattern.brightness, hold_ms: 1000, transition_id: null, keys: pattern.keys }],
});

/** A saved per-key scheme's first step, opened in the editor. */
export function patternFromScheme(scheme: Scheme): Pattern | null {
  const step = scheme.kind === "keys" ? scheme.steps[0] : undefined;
  if (!step?.color) return null;
  return { background: step.color, brightness: step.brightness, keys: { ...(step.keys ?? {}) } };
}

/** A rainbow along x: the quickest way to see every key or LED answer. */
export function rainbow(pattern: Pattern, leds: Led[]): Pattern {
  if (!leds.length) return pattern;
  const xs = leds.map((led) => led.x);
  const [low, high] = [Math.min(...xs), Math.max(...xs)];
  const keys = Object.fromEntries(
    leds.map((led) => {
      const hue = high > low ? ((led.x - low) / (high - low)) * 300 : 0;
      return [led.key, hsl(hue)];
    }),
  );
  return { ...pattern, keys };
}

function hsl(hue: number): string {
  const f = (n: number) => {
    const k = (n + hue / 30) % 12;
    const value = 0.5 - 0.5 * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(value * 255).toString(16).padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`.toUpperCase();
}

// Effects -------------------------------------------------------------------------------------------------
// The same motion the backend plays (services/playback.py, Motion), drawn on screen to preview a pattern.

export const EFFECTS: { type: EffectType; label: string; hint: string }[] = [
  { type: "blink", label: "Blink", hint: "On and off, half a cycle each" },
  { type: "strobe", label: "Strobe", hint: "A short flash each cycle" },
  { type: "breathe", label: "Breathe", hint: "Swells smoothly to dark and back" },
  { type: "glow", label: "Glow", hint: "A gentle swell, never dark" },
  { type: "rainbow", label: "Rainbow", hint: "Every hue in turn" },
];

const FRAME_S = 0.12;
const GLOW_LOW = 0.33;

const toRgb = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
const toHex = (rgb: number[]) => `#${rgb.map((c) => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, "0")).join("")}`.toUpperCase();

/** Where in its cycle an effect is for the ``index``th key (0..1). */
const phaseOf = (effect: Effect, t: number, index: number) => {
  const period = (effect.period_ms ?? 1000) / 1000;
  const value = (t - index * ((effect.stagger_ms ?? 0) / 1000)) / period;
  return value - Math.floor(value);
};

/** 1 when showing the effect's color, 0 when showing its other color. */
export function effectLevel(effect: Effect, t: number, index = 0): number {
  const phase = phaseOf(effect, t, index);
  const period = (effect.period_ms ?? 1000) / 1000;
  if (effect.type === "blink") return phase < 0.5 ? 1 : 0;
  if (effect.type === "strobe") return phase * period < Math.min(period / 2, Math.max(FRAME_S, period / 8)) ? 1 : 0;
  return 0.5 + 0.5 * Math.cos(2 * Math.PI * phase);
}

/** What a key whose own color is ``base`` shows ``t`` seconds in. */
export function effectColor(effect: Effect, base: string, t: number, index = 0): string {
  if (effect.type === "rainbow") return hsl(phaseOf(effect, t, index) * 360);
  const start = toRgb(effect.color ?? base);
  const end = effect.to ? toRgb(effect.to) : effect.type === "glow" ? start.map((c) => c * GLOW_LOW) : [0, 0, 0];
  const level = effectLevel(effect, t, index);
  return toHex(start.map((a, i) => end[i] + (a - end[i]) * level));
}

/** The pattern as it looks ``t`` seconds into playing, with every key drawn (``all`` is the device's keys). */
export function animate(pattern: Pattern, effects: Effect[], t: number, all: string[]): Pattern {
  if (!effects.length) return pattern;
  const keys = { ...pattern.keys };
  for (const effect of effects) {
    const names = effect.keys?.length ? effect.keys : all;
    names.forEach((name, index) => (keys[name] = effectColor(effect, keys[name] ?? pattern.background, t, effect.keys?.length ? index : 0)));
  }
  return { ...pattern, keys };
}

/** Keys from left to right (then top to bottom), so a stagger runs across the keyboard like a wave. */
export const leftToRight = (names: string[], leds: Led[]) => {
  const at = new Map(leds.map((led) => [led.key, led]));
  return [...names].filter((name) => at.has(name)).sort((a, b) => at.get(a)!.x - at.get(b)!.x || at.get(a)!.y - at.get(b)!.y);
};

/** A pattern, and what moves on it, saved as a per-key scheme that plays until stopped. */
export const animatedScheme = (name: string, pattern: Pattern, effects: Effect[]) => {
  const scheme = schemeFromPattern(name, pattern);
  if (!effects.length) return scheme;
  return { ...scheme, loops: true, steps: [{ ...scheme.steps[0], hold_ms: 0, effects }] };
};

/** A saved per-key scheme's effects, to edit them with its pattern. */
export const effectsFromScheme = (scheme: Scheme): Effect[] => (scheme.kind === "keys" ? scheme.steps[0]?.effects ?? [] : []);

/** A key press in the browser as a hotkey ("Ctrl+Alt+1"), or null while only modifiers are down. */
export function comboOf(event: Pick<KeyboardEvent, "code" | "ctrlKey" | "altKey" | "shiftKey" | "metaKey">): string | null {
  const named: Record<string, string> = {
    Space: "Space", Enter: "Enter", NumpadEnter: "Enter", Tab: "Tab", Escape: "Escape", Backspace: "Backspace",
    Insert: "Insert", Delete: "Delete", Home: "Home", End: "End", PageUp: "PageUp", PageDown: "PageDown",
    ArrowUp: "Up", ArrowDown: "Down", ArrowLeft: "Left", ArrowRight: "Right", PrintScreen: "PrintScreen", Pause: "Pause",
    NumpadMultiply: "NumMultiply", NumpadAdd: "NumAdd", NumpadSubtract: "NumSubtract", NumpadDivide: "NumDivide",
    NumpadDecimal: "NumDecimal", AudioVolumeUp: "VolumeUp", AudioVolumeDown: "VolumeDown", AudioVolumeMute: "VolumeMute",
    MediaPlayPause: "MediaPlayPause", MediaTrackNext: "MediaNext", MediaTrackPrevious: "MediaPrevious", MediaStop: "MediaStop",
  };
  const code = event.code;
  const key = named[code] ?? (/^Key[A-Z]$/.test(code) ? code.slice(3) : /^Digit\d$/.test(code) ? code.slice(5)
    : /^Numpad\d$/.test(code) ? `Num${code.slice(6)}` : /^F\d{1,2}$/.test(code) ? code : null);
  if (!key) return null;
  const modifiers = [event.ctrlKey && "Ctrl", event.altKey && "Alt", event.shiftKey && "Shift", event.metaKey && "Win"].filter(Boolean);
  return [...modifiers, key].join("+");
}
