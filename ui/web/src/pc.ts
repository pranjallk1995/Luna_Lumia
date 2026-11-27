/** The PC tab: keyboard keys and case LEDs, each painted its own color. */

import type { Light, Scheme } from "./api";

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

/** The label printed on a key: "Esc" for Escape, "7" for Keypad7, "↑" for UpArrow. */
export function keyLabel(name: string): string {
  if (SHORT[name]) return SHORT[name];
  if (/^Keypad\d$/.test(name)) return name.slice(-1);
  if (/^LED \d+$/.test(name)) return name.slice(4);
  return name.length > 4 ? name.slice(0, 4) : name;
}

/** The SVG view box that holds every key or LED, with room for a key around each center. */
export function viewBox(leds: Led[], keyboard: boolean): string {
  if (!leds.length) return "0 0 10 10";
  const pad = keyboard ? 6 : 1;
  const xs = leds.map((led) => led.x);
  const ys = leds.map((led) => led.y);
  const [left, top] = [Math.min(...xs) - pad, Math.min(...ys) - pad];
  return `${left} ${top} ${Math.max(...xs) + pad - left} ${Math.max(...ys) + pad - top}`;
}

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
