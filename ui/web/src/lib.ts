/** Small helpers shared across the app. */

/** The server's reason for a failure, or a fallback when there is none. */
export const messageOf = (failure: unknown, fallback: string): string =>
  (failure instanceof Error && failure.message) || fallback;

/** A remembered choice; the app works the same when browser storage is unavailable. */
export function remembered<T extends string>(key: string, allowed: readonly T[], fallback: T): T {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : fallback;
  } catch {
    return fallback;
  }
}

export function remember(key: string, value: string): void {
  try {
    localStorage.setItem(key, value);
  } catch {
    // A private window may refuse storage; the choice just lasts until reload.
  }
}
