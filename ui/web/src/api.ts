/** The backend routes the gateway forwards, and the hooks that keep the dashboard in step with them. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { useToast } from "./components/Toasts";
import { post, put, remove, request } from "./http";
import { messageOf } from "./lib";
import type { LightLeds } from "./pc";

export type Settings = {
  version: string;
  preset_colors: Record<string, string>;
  temperature_presets: string[];
  weekday_names: string[];
  min_color_temp: number;
  max_color_temp: number;
  default_color_temp: number;
  discovery_broadcast: string;
  name_max_chars: number;
  max_sequence_steps: number;
  picture_size: [number, number];
  picture_types: string[];
};

export type Light = {
  id: number;
  name: string;
  ip_address: string;
  mac_address?: string | null;
  protocol?: string;
  device?: string | null;
  /** Part of an OpenRGB device: a zone (header) number or name, and a range of its LEDs. */
  zone?: string | null;
  leds?: string | null;
  is_on: boolean;
  brightness: number;
  color: string;
  color_temp?: number | null;
  reachable: boolean | null;
  last_seen?: string | null;
  effective_image_url?: string | null;
};

/** What a playing scheme is showing on a light right now. */
export type Frame = { brightness: number; color?: string; color_temp?: number };

export type Collection = {
  id: number;
  name: string;
  kind: "room" | "group";
  light_ids: number[];
  effective_image_url?: string | null;
};

export type Step = {
  color?: string | null;
  color_temp?: number | null;
  brightness: number;
  hold_ms?: number;
  transition_id?: number | null;
  /** Per-key schemes: keyboard keys (or groups such as "wasd") and their colors; color is every other key. */
  keys?: Record<string, string> | null;
};

export type Scheme = {
  id: number;
  name: string;
  kind: "solid" | "sequence" | "keys";
  is_preset: boolean;
  brightness: number;
  color?: string | null;
  color_temp?: number | null;
  loops: boolean;
  steps: Step[];
  cycle_ms?: number;
  preview_colors?: string[];
  /** How many keys a per-key scheme colors across its steps. */
  keys_colored?: number;
  weather_slots?: string[];
  music_moods?: string[];
};

export type Transition = { id: number; name: string; duration_ms: number; curve: string; is_preset: boolean };

export type Schedule = {
  id: number;
  name: string;
  kind: string;
  target_type: string;
  target_id?: number | null;
  action: string;
  scene_id?: number | null;
  time_mode?: "time" | "sunrise" | "sunset";
  run_time?: string | null;
  offset_minutes?: number;
  weekdays: number[];
  run_date?: string | null;
  last_run_date?: string | null;
  today_time?: string | null;
  enabled?: boolean;
};

export type Place = { name: string; latitude: number; longitude: number; sunrise?: string | null; sunset?: string | null };

export type Dashboard = {
  lights: Light[];
  rooms: Collection[];
  groups: Collection[];
  scenes: Scheme[];
  schedules: Schedule[];
  transitions: Transition[];
  location?: Place | null;
  playing: Record<string, number>;
  live: Record<string, Frame>;
  /** The room-image catalog: the picture each kind of room borrows when it has none of its own. */
  room_images: { room_key: string; image_url: string }[];
};

export type Discovered = { ip_address: string; mac_address?: string | null; suggested_name: string; moved_from?: string };
export type PcDevice = { ip_address: string; device: string; led_count: number; protocol: string; port: number; suggested_name: string };
export type PcSource = { available: boolean; error: string | null };
export type MovedPcLights = { scanned: string[]; moved: { id: number; name: string; from: string; to: string }[]; blocked: string[]; unchanged: string[]; ambiguous: { name: string; hosts: string[] }[]; not_found: string[] };
export type PcDiscovery = { ip_address: string; devices: PcDevice[]; warnings: string[]; openrgb: PcSource; icue: PcSource };
export type LightState = Partial<Pick<Light, "brightness" | "color" | "color_temp">> & { on?: boolean };
export type Target = { type: string; id: number | null };

const KEY = ["dashboard"];

export function useDashboard() {
  // Lights also change from schedules and assistants, and a playing scheme changes them constantly.
  return useQuery({
    queryKey: KEY,
    queryFn: () => request<Dashboard>("/api/dashboard"),
    refetchInterval: (query) => (Object.keys(query.state.data?.live ?? {}).length ? 1_000 : 3_000),
  });
}

export const lumia = {
  discover: (broadcast: string) => post<Discovered[]>("/api/discovery", { broadcast_space: broadcast }),
  discoverPc: (host: string) => post<PcDiscovery>("/api/discovery/pc", { host }),
  findMovedPcLights: () => post<MovedPcLights>("/api/discovery/pc/moved", {}),
  refreshLights: () => post("/api/lights/refresh"),
  create: (resource: string, payload: unknown) => post(`/api/${resource}`, payload),
  update: (resource: string, id: number, payload: unknown) => put(`/api/${resource}/${id}`, payload),
  delete: (resource: string, id: number) => remove(`/api/${resource}/${id}`),
  control: ({ type, id }: Target, state: LightState) => post(`/api/control/${type}`, { target_id: id, state }),
  applyScheme: (schemeId: number, { type, id }: Target) =>
    post<{ scene?: string; light_ids?: number[] }>(`/api/scenes/${schemeId}/apply`, { target_type: type, target_id: id }),
  stopSchemes: ({ type, id }: Target) => post("/api/scenes/stop", { target_type: type, target_id: id }),
  saveLocation: (place: Pick<Place, "name" | "latitude" | "longitude">) => put("/api/location", place),
  /** Rename a light, then re-infer its background from the new name, unless it has a picture of its own. */
  renameLight: async (id: number, name: string, keepPicture = false) => {
    await put(`/api/lights/${id}`, { name });
    if (!keepPicture) await put(`/api/lights/${id}/background`, { image_url: null });
  },
  /** Store a picture in Luna Visia and show it on a light, room, or group. */
  storePicture: (kind: "light" | "room" | "group", id: number, dataUrl: string) =>
    post(`/api/${kind}s/${id}/background-image`, { content_base64: dataUrl.slice(dataUrl.indexOf(",") + 1) }),
  addLights: (kind: string, id: number, lightIds: number[]) => post(`/api/${kind}s/${id}/lights`, { light_ids: lightIds }),
  removeLight: (kind: string, id: number, lightId: number) => remove(`/api/${kind}s/${id}/lights/${lightId}`),
  /** Show a pattern on a PC light now: each named key or LED its own color, the rest the background. */
  paintLeds: (lightId: number, payload: { color: string; brightness: number; keys: Record<string, string> }) =>
    put(`/api/lights/${lightId}/leds`, payload),
};

/** A PC light's keys (keyboards) or LEDs (case parts) with their places, for the PC tab. */
export const useLightLeds = (lightId: number) =>
  useQuery({ queryKey: ["leds", lightId], queryFn: () => request<LightLeds>(`/api/lights/${lightId}/leds`), retry: 1, staleTime: 5 * 60_000 });

/** Run a change, then refresh the dashboard; a refusal becomes a toast, and the result says which. */
export function useAct() {
  const client = useQueryClient();
  const toast = useToast();
  return useCallback(
    async (action: () => Promise<unknown>, fallback = "That did not work. Please try again.") => {
      try {
        await action();
        return true;
      } catch (failure) {
        toast(messageOf(failure, fallback));
        return false;
      } finally {
        client.invalidateQueries({ queryKey: KEY });
      }
    },
    [client, toast],
  );
}

const asLightFields = ({ on, ...rest }: LightState): Partial<Light> => (on === undefined ? rest : { ...rest, is_on: on });

/** Change lights: shown on screen at once, undone if the backend or a bulb refuses. */
export function useControl() {
  const client = useQueryClient();
  const act = useAct();
  return useCallback(
    (target: Target, state: LightState, affected: (light: Light) => boolean, fallback?: string) => {
      const previous = client.getQueryData<Dashboard>(KEY);
      if (previous) {
        client.setQueryData<Dashboard>(KEY, {
          ...previous,
          lights: previous.lights.map((light) => (affected(light) ? { ...light, ...asLightFields(state) } : light)),
        });
      }
      return act(async () => {
        await client.cancelQueries({ queryKey: KEY });
        try {
          await lumia.control(target, state);
        } catch (failure) {
          if (previous) client.setQueryData(KEY, previous);
          throw failure;
        }
      }, fallback);
    },
    [act, client],
  );
}
