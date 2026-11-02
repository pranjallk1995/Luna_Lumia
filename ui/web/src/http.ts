/** Talking to the gateway: JSON requests, their errors, and who is signed in. */

import { useQuery } from "@tanstack/react-query";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

type ValidationDetail = { msg?: string; loc?: (string | number)[] };

/** One readable validation failure, such as "Step 2 brightness: ...". */
export function validationReason({ msg = "", loc = [] }: ValidationDetail): string {
  const message = msg.replace(/^Value error, /, "");
  const parts: string[] = [];
  for (const part of loc) {
    if (typeof part === "number") {
      const owner = parts.pop();
      parts.push(`${owner ? owner.replace(/s$/, "") : "item"} ${part + 1}`);
    } else {
      parts.push(part.replace(/_/g, " "));
    }
  }
  const field = parts.join(" ");
  return field ? `${field[0].toUpperCase()}${field.slice(1)}: ${message}` : message;
}

/** The backend's reason for rejecting a request, not just "Invalid request". */
function reasonOf(body: { error?: string; details?: ValidationDetail[] } | null): string {
  const reasons = (body?.details ?? []).map(validationReason);
  return reasons.length ? reasons.join("; ") : (body?.error ?? "The request failed. Please try again.");
}

export async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: init?.body ? { "Content-Type": "application/json" } : undefined,
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(reasonOf(body), response.status);
  }
  return body as T;
}

export const post = <T>(path: string, body?: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) });

export const put = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "PUT", body: JSON.stringify(body) });

export const remove = <T>(path: string) => request<T>(path, { method: "DELETE" });

export type Session<S> =
  | { status: "signed_out"; login_url: string }
  | { status: "forbidden"; email?: string; logout_url: string }
  | { status: "signed_in"; email?: string; logout_url: string; settings: S };

export function useSession<S>() {
  return useQuery({
    queryKey: ["session"],
    queryFn: () => request<Session<S>>("/auth/session"),
    staleTime: 60_000,
  });
}
