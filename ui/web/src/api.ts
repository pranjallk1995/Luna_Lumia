/** The backend routes the gateway forwards, and the hooks that keep the dashboard in step with them. */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";

import { useToast } from "./components/Toasts";
import { post, put, remove, request } from "./http";
import { messageOf } from "./lib";

export type Settings = {
  preset_colors: Record<string, string>;
  temperature_presets: string[];
  weekday_names: string[];
  min_color_temp: number;
  max_color_temp: number;
  default_color_temp: number;
  discovery_broadcast: string;
  name_max_chars: number;
  max_sequence_steps: number;
};

export type Light = {
  id: number;
  name: string;
  ip_address: string;
  mac_address?: string | null;
  protocol?: string;
  device?: string | null;
  is_on: boolean;
  brightness: number;
  color: string;
  color_temp?: number | null;
  reachable: boolean | null;
  last_seen?: string | null;
  effective_image_url?: string | null;
};

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
};

export type Scheme = {
  id: number;
  name: string;
  kind: "solid" | "sequence";
  is_preset: boolean;
  brightness: number;
  color?: string | null;
  color_temp?: number | null;
  loops: boolean;
  steps: Step[];
  cycle_ms?: number;
  preview_colors?: string[];
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
};

export type Discovered = { ip_address: string; mac_address?: string | null; suggested_name: string };
export type PcDevice = { ip_address: string; device: string; led_count: number; protocol: string; port: number; suggested_name: string };
export type PcSource = { available: boolean; error: string | null };
export type PcDiscovery = { ip_address: string; devices: PcDevice[]; warnings: string[]; openrgb: PcSource; icue: PcSource };
export type LightState = Partial<Pick<Light, "brightness" | "color" | "color_temp">> & { on?: boolean };
export type Target = { type: string; id: number | null };

const KEY = ["dashboard"];

export function useDashboard() {
  // A page left open still moves on to the next day's sunrise and sunset.
  return useQuery({ queryKey: KEY, queryFn: () => request<Dashboard>("/api/dashboard"), refetchInterval: 60_000 });
}

export const lumia = {
  discover: (broadcast: string) => post<Discovered[]>("/api/discovery", { broadcast_space: broadcast }),
  discoverPc: (host: string) => post<PcDiscovery>("/api/discovery/pc", { host }),
  refreshLights: () => post("/api/lights/refresh"),
  create: (resource: string, payload: unknown) => post(`/api/${resource}`, payload),
  update: (resource: string, id: number, payload: unknown) => put(`/api/${resource}/${id}`, payload),
  delete: (resource: string, id: number) => remove(`/api/${resource}/${id}`),
  control: ({ type, id }: Target, state: LightState) => post(`/api/control/${type}`, { target_id: id, state }),
  applyScheme: (schemeId: number, { type, id }: Target) =>
    post<{ scene?: string; light_ids?: number[] }>(`/api/scenes/${schemeId}/apply`, { target_type: type, target_id: id }),
  stopSchemes: ({ type, id }: Target) => post("/api/scenes/stop", { target_type: type, target_id: id }),
  saveLocation: (place: Pick<Place, "name" | "latitude" | "longitude">) => put("/api/location", place),
  /** Rename a light, then re-infer its background from the new name. */
  renameLight: async (id: number, name: string) => {
    await put(`/api/lights/${id}`, { name });
    await put(`/api/lights/${id}/background`, { image_url: null });
  },
  addLights: (kind: string, id: number, lightIds: number[]) => post(`/api/${kind}s/${id}/lights`, { light_ids: lightIds }),
  removeLight: (kind: string, id: number, lightId: number) => remove(`/api/${kind}s/${id}/lights/${lightId}`),
};

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
