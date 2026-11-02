import { Bolt, CirclePlus, DoorOpen, Lightbulb, Palette, Radar, Sun, Thermometer, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { lumia, useAct, useControl, type Dashboard, type Discovered, type Light, type Settings } from "../api";
import { imageStyle, isValidName, mostCommon, roomsByLight, temperatureSchemes } from "../dashboard";
import { messageOf } from "../lib";
import { ColorChips, ColorInput, ModeToggle, NameEditor, Slider, TemperatureChips, Toggle, type Mode } from "./controls";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

function FoundLight({ bulb, added, settings }: { bulb: Discovered; added: boolean; settings: Settings }) {
  const [name, setName] = useState(bulb.suggested_name);
  const act = useAct();
  const add = () =>
    act(() => lumia.create("lights", { name, ip_address: bulb.ip_address, protocol: "wiz", mac_address: bulb.mac_address }));
  return (
    <div className="ll-found">
      <label className="lv-field">
        {bulb.ip_address} · {bulb.mac_address || "MAC unavailable"}
        <input className="lv-input" value={name} disabled={added} maxLength={settings.name_max_chars} onChange={(event) => setName(event.target.value)} />
      </label>
      <button className="lv-button" type="button" disabled={added} onClick={add}>
        {added ? "Added" : "Add"}
      </button>
    </div>
  );
}

function Discovery({ dashboard, settings }: TabProps) {
  const client = useQueryClient();
  const toast = useToast();
  const [scanning, setScanning] = useState(false);
  // Kept in the cache, so the results survive a visit to another tab.
  const { data: found } = useQuery<Discovered[]>({ queryKey: ["discovered"], enabled: false });

  const scan = async () => {
    setScanning(true);
    try {
      client.setQueryData(["discovered"], await lumia.discover(settings.discovery_broadcast));
    } catch (failure) {
      toast(`Network scan failed: ${messageOf(failure, "please try again.")}`);
    } finally {
      setScanning(false);
    }
  };

  const configured = new Set(dashboard.lights.map((light) => light.ip_address));
  return (
    <section className="lv-panel">
      <div className="ll-scan">
        <span className="ll-scan-icon">
          <Lightbulb size={22} />
        </span>
        <div>
          <h2>Find lights on your network</h2>
          <p className="lv-caption">Scans for WiZ-compatible lights. Nothing is added automatically.</p>
        </div>
        <button className="lv-button" type="button" disabled={scanning} onClick={scan}>
          <Radar size={17} />
          {scanning ? "Scanning…" : "Scan for lights"}
        </button>
      </div>
      {found && (
        <div className="ll-found-list">
          <h3>Found lights ({found.length})</h3>
          {!found.length && (
            <p className="lv-alert">No WiZ lights answered the scan. Confirm they are powered on and connected to the network.</p>
          )}
          {found.map((bulb) => (
            <FoundLight bulb={bulb} added={configured.has(bulb.ip_address)} settings={settings} key={bulb.ip_address} />
          ))}
        </div>
      )}
    </section>
  );
}

function AllLights({ dashboard, settings }: TabProps) {
  const control = useControl();
  const act = useAct();
  const [mode, setMode] = useState<Mode>("temperature");
  const lights = dashboard.lights;
  const on = lights.filter((light) => light.is_on);
  const none = !on.length;
  const online = lights.filter((light) => light.reachable === true).length;
  const isOn = (light: Light) => light.is_on;
  const target = { type: "on", id: null };
  const fallback = "Could not update all lights.";
  const schemes = temperatureSchemes(dashboard.scenes, settings.temperature_presets);

  return (
    <div className="ll-all">
      <div className="ll-stats">
        <div className="ll-stat">
          <Bolt size={18} />
          <div>
            <strong>{lights.length}</strong>
            <small>Total lights</small>
          </div>
        </div>
        <div className="ll-stat">
          <span className="ll-orb ll-orb-on" />
          <div>
            <strong>{on.length}</strong>
            <small>On</small>
          </div>
        </div>
        <div className="ll-stat">
          <span className="ll-orb ll-orb-online" />
          <div>
            <strong>{online}</strong>
            <small>Online</small>
          </div>
        </div>
      </div>
      <div className="ll-all-box">
        <Slider
          label="All lights brightness"
          icon={Sun}
          min={1}
          max={100}
          value={mostCommon(on.map((light) => light.brightness), 100)}
          disabled={none}
          onCommit={(brightness) => control(target, { brightness }, isOn, fallback)}
        />
      </div>
      <div className="ll-all-box">
        <div className="ll-all-mode">
          <ModeToggle mode={mode} onChange={setMode} />
          {mode === "temperature" ? (
            <Slider
              label="All lights temperature"
              min={settings.min_color_temp}
              max={settings.max_color_temp}
              step={100}
              unit="K"
              value={mostCommon(on.map((light) => light.color_temp), settings.default_color_temp)}
              disabled={none}
              onCommit={(color_temp) => control(target, { color_temp }, isOn, fallback)}
            />
          ) : (
            <ColorInput
              label="All lights color"
              value={mostCommon(on.map((light) => light.color), "#FFFFFF")}
              disabled={none}
              onCommit={(color) => control(target, { color }, isOn, fallback)}
            />
          )}
        </div>
        {mode === "temperature" ? (
          <TemperatureChips schemes={schemes} disabled={none} onPick={(scheme) => act(() => lumia.applyScheme(scheme.id, target), fallback)} />
        ) : (
          <ColorChips settings={settings} disabled={none} onPick={(color) => control(target, { color }, isOn, fallback)} />
        )}
      </div>
    </div>
  );
}

function LightCard({ light, dashboard, settings, rooms }: TabProps & { light: Light; rooms: string[] }) {
  const control = useControl();
  const act = useAct();
  const [mode, setMode] = useState<Mode>("temperature");
  const target = { type: "light", id: light.id };
  const fallback = "Could not update this light.";
  const send = (state: Parameters<typeof control>[1]) => control(target, state, (other) => other.id === light.id, fallback);
  const reachability = light.reachable ? "Online" : light.reachable === null ? "Status unknown" : "Offline";
  const schemes = temperatureSchemes(dashboard.scenes, settings.temperature_presets);

  return (
    <article className="ll-card">
      <div className="ll-hero" style={imageStyle(light.effective_image_url)}>
        {light.is_on && <span className="ll-power-on" aria-label="Light on" />}
        <span className={light.reachable ? "ll-status ll-status-online" : "ll-status"}>
          <i />
          {reachability}
        </span>
      </div>
      <div className="ll-card-body">
        <NameEditor
          name={light.name}
          entity="Light"
          maxChars={settings.name_max_chars}
          onRename={(name) => act(() => lumia.renameLight(light.id, name))}
        />
        <p className="ll-meta">
          {light.ip_address} · {light.mac_address || "MAC not discovered"}
        </p>
        <Toggle label="On" checked={light.is_on} onChange={(on) => send({ on })} />
        <Slider label="Brightness" icon={Sun} min={1} max={100} value={light.brightness} onCommit={(brightness) => send({ brightness })} />
        <ModeToggle mode={mode} onChange={setMode} />
        <div className="ll-mode-body">
          {mode === "temperature" ? (
            <>
              <Slider
                label="Color temperature"
                icon={Thermometer}
                min={settings.min_color_temp}
                max={settings.max_color_temp}
                step={100}
                unit="K"
                value={light.color_temp || settings.default_color_temp}
                onCommit={(color_temp) => send({ color_temp })}
              />
              <TemperatureChips schemes={schemes} onPick={(scheme) => act(() => lumia.applyScheme(scheme.id, target), fallback)} />
            </>
          ) : (
            <>
              <div className="ll-slider">
                <Palette size={17} aria-hidden="true" />
                <ColorInput value={light.color} onCommit={(color) => send({ color })} />
              </div>
              <ColorChips settings={settings} onPick={(color) => send({ color })} />
            </>
          )}
        </div>
        <div className="ll-card-footer">
          <span className="ll-membership">
            {rooms.length > 0 && (
              <>
                <DoorOpen size={14} />
                {rooms.join(", ")}
              </>
            )}
          </span>
          <button className="lv-icon-button" type="button" aria-label={`Delete ${light.name}`} onClick={() => act(() => lumia.delete("lights", light.id))}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>
    </article>
  );
}

function AddLight({ settings }: { settings: Settings }) {
  const [error, setError] = useState("");
  const act = useAct();

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const name = String(fields.get("name"));
    if (!isValidName(name)) {
      setError("Light name may contain only letters, numbers, and spaces.");
      return;
    }
    setError("");
    const added = await act(() => lumia.create("lights", { name, ip_address: String(fields.get("ip")), protocol: "wiz" }));
    if (added) form.reset();
  };

  return (
    <details className="lv-panel ll-details">
      <summary>
        <CirclePlus size={17} />
        Add a light
      </summary>
      <form className="lv-form" onSubmit={submit}>
        <label className="lv-field">
          Name
          <input className="lv-input" name="name" placeholder="Bedroom lamp" maxLength={settings.name_max_chars} required />
        </label>
        <label className="lv-field">
          IP address
          <input className="lv-input" name="ip" placeholder="192.168.1.20" required />
        </label>
        {error && <p className="lv-alert lv-alert-error">{error}</p>}
        <button className="lv-button" type="submit">
          Add light
        </button>
      </form>
    </details>
  );
}

export function LightsTab({ dashboard, settings }: TabProps) {
  const rooms = roomsByLight(dashboard);
  return (
    <>
      <Discovery dashboard={dashboard} settings={settings} />
      <AllLights dashboard={dashboard} settings={settings} />
      <div className="ll-grid">
        {dashboard.lights.map((light) => (
          <LightCard light={light} dashboard={dashboard} settings={settings} rooms={rooms[light.id] ?? []} key={light.id} />
        ))}
      </div>
      <AddLight settings={settings} />
    </>
  );
}
