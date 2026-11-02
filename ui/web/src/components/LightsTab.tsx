import { CirclePlus, DoorOpen, House, Palette, Radar, RefreshCw, Sun, Thermometer, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { lumia, useAct, useControl, type Dashboard, type Discovered, type Light, type Settings } from "../api";
import { isValidName, lightColor, lightState, mostCommon, roomOf, temperatureSchemes } from "../dashboard";
import { messageOf } from "../lib";
import { Bulb, ColorChips, ColorInput, ModeToggle, NameEditor, SectionHead, Slider, TemperatureChips, Toggle, type Mode } from "./controls";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

const lastSeen = (light: Light) =>
  light.last_seen
    ? new Date(light.last_seen).toLocaleString("en-GB", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit", hour12: true })
    : null;

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

/** The network scan and manual entry, together, out of the way once the lights are set up. */
function AddLights({ dashboard, settings, onClose }: TabProps & { onClose: () => void }) {
  const client = useQueryClient();
  const toast = useToast();
  const act = useAct();
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");
  // Kept in the cache, so the results survive closing the dialog.
  const { data: found } = useQuery<Discovered[]>({ queryKey: ["discovered"], enabled: false });
  const configured = new Set(dashboard.lights.map((light) => light.ip_address));

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

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    const name = String(fields.get("name"));
    if (!isValidName(name)) return setError("Light name may contain only letters, numbers, and spaces.");
    setError("");
    if (await act(() => lumia.create("lights", { name, ip_address: String(fields.get("ip")), protocol: "wiz" }))) form.reset();
  };

  const fresh = (found ?? []).filter((bulb) => !configured.has(bulb.ip_address));
  return (
    <Dialog title="Add lights" size="large" onClose={onClose}>
      <div className="lv-form">
        <div className="ll-scan">
          <Radar size={20} />
          <div>
            <strong>Find lights on your network</strong>
            <p className="lv-caption">Scans {settings.discovery_broadcast} for WiZ lights. Nothing is added until you choose.</p>
          </div>
          <button className="lv-button" type="button" disabled={scanning} onClick={scan}>
            {scanning ? "Scanning…" : "Scan"}
          </button>
        </div>
        {found && (
          <div className="ll-found-list">
            {!found.length && <p className="lv-alert">No WiZ lights answered. Check they are powered on and on this network.</p>}
            {found.length > 0 && !fresh.length && <p className="lv-caption">Found {found.length} lights. All of them are already added.</p>}
            {found.map((bulb) => (
              <FoundLight bulb={bulb} added={configured.has(bulb.ip_address)} settings={settings} key={bulb.ip_address} />
            ))}
          </div>
        )}
        <form className="lv-form" onSubmit={submit}>
          <p className="lv-caption">Or add one by its address</p>
          <div className="lv-form-row">
            <label className="lv-field">
              Name
              <input className="lv-input" name="name" placeholder="Bedroom lamp" maxLength={settings.name_max_chars} required />
            </label>
            <label className="lv-field">
              IP address
              <input className="lv-input" name="ip" placeholder="192.168.1.20" required />
            </label>
          </div>
          {error && <p className="lv-alert lv-alert-error">{error}</p>}
          <button className="lv-button lv-button-primary" type="submit">
            <CirclePlus size={17} />
            Add light
          </button>
        </form>
      </div>
    </Dialog>
  );
}

/** Every light that is on, at once, with a count of the whole house. */
function HouseSummary({ dashboard, settings }: TabProps) {
  const control = useControl();
  const act = useAct();
  const lights = dashboard.lights;
  const on = lights.filter((light) => lightState(light) === "on");
  const offline = lights.filter((light) => lightState(light) === "offline");
  const none = !on.length;
  const isOn = (light: Light) => light.is_on;
  const target = { type: "on", id: null };
  const fallback = "Could not update the lights that are on.";
  const schemes = temperatureSchemes(dashboard.scenes, settings.temperature_presets);

  return (
    <section className="ll-house" aria-label="Whole house">
      <div className="ll-panel ll-house-count">
        <span className="ll-label">
          <House size={15} />
          Whole house
        </span>
        <strong>
          {on.length} <small>of {lights.length} on</small>
        </strong>
        <span className="ll-label">
          {offline.length > 0 && <span className="ll-bad">{offline.length} offline · </span>}
          {lights.length - offline.length} online
        </span>
        <span className="ll-dots" aria-hidden="true">
          {lights.map((light) => (
            <Bulb color={lightColor(light)} state={lightState(light)} small key={light.id} />
          ))}
        </span>
      </div>
      <div className="ll-panel ll-house-controls">
        <div className="ll-row">
          <span>Brightness</span>
          <Slider
            label="Brightness of every light that is on"
            icon={Sun}
            min={1}
            max={100}
            unit="%"
            value={mostCommon(on.map((light) => light.brightness), 100)}
            disabled={none}
            onCommit={(brightness) => control(target, { brightness }, isOn, fallback)}
          />
        </div>
        <div className="ll-row">
          <span>Temperature</span>
          <Slider
            label="Temperature of every light that is on"
            icon={Thermometer}
            min={settings.min_color_temp}
            max={settings.max_color_temp}
            step={100}
            unit="K"
            value={mostCommon(on.map((light) => light.color_temp), settings.default_color_temp)}
            disabled={none}
            onCommit={(color_temp) => control(target, { color_temp }, isOn, fallback)}
          />
        </div>
        <div className="ll-row">
          <span>Presets</span>
          <TemperatureChips schemes={schemes} disabled={none} onPick={(scheme) => act(() => lumia.applyScheme(scheme.id, target), fallback)} />
        </div>
        <div className="ll-row">
          <span>Colors</span>
          <ColorChips settings={settings} disabled={none} onPick={(color) => control(target, { color }, isOn, fallback)} />
        </div>
        <p className="lv-caption">{none ? "Turn a light on to adjust it." : "Changes every light that is on."}</p>
      </div>
    </section>
  );
}

function DeleteLight({ light, room, onClose }: { light: Light; room?: string; onClose: () => void }) {
  const act = useAct();
  return (
    <Dialog title={`Delete ${light.name}?`} onClose={onClose}>
      <p className="lv-confirm-text">
        It also leaves {room ?? "its rooms"} and any groups. You can add it again later by scanning.
      </p>
      <div className="lv-confirm-actions">
        <button className="lv-button" type="button" onClick={onClose}>
          Cancel
        </button>
        <button className="lv-button ll-danger" type="button" onClick={() => act(() => lumia.delete("lights", light.id)).then(onClose)}>
          <Trash2 size={16} />
          Delete light
        </button>
      </div>
    </Dialog>
  );
}

function LightCard({ light, dashboard, settings }: TabProps & { light: Light }) {
  const control = useControl();
  const act = useAct();
  const [mode, setMode] = useState<Mode>(light.color_temp ? "temperature" : "color");
  const [open, setOpen] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const state = lightState(light);
  const offline = state === "offline";
  const room = roomOf(dashboard, light.id)?.name;
  const target = { type: "light", id: light.id };
  const fallback = `Could not update ${light.name}.`;
  const send = (change: Parameters<typeof control>[1]) => control(target, change, (other) => other.id === light.id, fallback);
  const schemes = temperatureSchemes(dashboard.scenes, settings.temperature_presets);
  const seen = lastSeen(light);

  return (
    <article className={offline ? "ll-panel ll-light ll-light-offline" : "ll-panel ll-light"}>
      <div className="ll-light-top">
        <Bulb color={lightColor(light)} state={state} />
        <div className="ll-light-name">
          <span className="ll-room-tag">
            <DoorOpen size={12} />
            {room ?? "Not in a room"}
          </span>
          <NameEditor name={light.name} entity="Light" maxChars={settings.name_max_chars} onRename={(name) => act(() => lumia.renameLight(light.id, name))} />
          {offline ? (
            <span className="ll-bad">Offline{seen ? ` · last seen ${seen}` : ""}</span>
          ) : (
            <span>{light.is_on ? `On · ${light.brightness}% · ${light.color_temp ? `${light.color_temp} K` : light.color}` : "Off"}</span>
          )}
        </div>
        <Toggle label={`${light.name} on`} hideLabel checked={light.is_on && !offline} disabled={offline} onChange={(on) => send({ on })} />
      </div>
      {offline ? (
        <button className="lv-button ll-small-button" type="button" onClick={() => act(lumia.refreshLights, "The lights could not be checked.")}>
          <RefreshCw size={15} />
          Check again
        </button>
      ) : (
        <Slider label={`${light.name} brightness`} icon={Sun} min={1} max={100} unit="%" value={light.brightness} disabled={!light.is_on} onCommit={(brightness) => send({ brightness })} />
      )}
      <button className="ll-link-button" type="button" aria-expanded={open} onClick={() => setOpen(!open)}>
        {open ? "Done" : "Adjust"}
      </button>
      {open && (
        <div className="ll-light-more">
          <ModeToggle mode={mode} onChange={setMode} />
          {mode === "temperature" ? (
            <>
              <Slider
                label={`${light.name} temperature`}
                icon={Thermometer}
                min={settings.min_color_temp}
                max={settings.max_color_temp}
                step={100}
                unit="K"
                value={light.color_temp || settings.default_color_temp}
                disabled={offline}
                onCommit={(color_temp) => send({ color_temp })}
              />
              <TemperatureChips schemes={schemes} disabled={offline} onPick={(scheme) => act(() => lumia.applyScheme(scheme.id, target), fallback)} />
            </>
          ) : (
            <div className="ll-color-row">
              <Palette size={17} aria-hidden="true" />
              <ColorInput label={`${light.name} color`} value={light.color} disabled={offline} onCommit={(color) => send({ color })} />
              <ColorChips settings={settings} disabled={offline} onPick={(color) => send({ color })} />
            </div>
          )}
          <div className="ll-light-foot">
            <span className="ll-meta">
              {light.ip_address} · {light.mac_address || "MAC not discovered"}
            </span>
            <button className="lv-icon-button" type="button" aria-label={`Delete ${light.name}`} title="Delete" onClick={() => setDeleting(true)}>
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      )}
      {deleting && <DeleteLight light={light} room={room} onClose={() => setDeleting(false)} />}
    </article>
  );
}

export function LightsTab({ dashboard, settings }: TabProps) {
  const [adding, setAdding] = useState(false);
  // Sorted by room, with the room on each card: most rooms hold one light, so a heading per room would leave rows nearly empty.
  const roomName = (light: Light) => roomOf(dashboard, light.id)?.name ?? "￿";
  const lights = [...dashboard.lights].sort((a, b) => roomName(a).localeCompare(roomName(b)) || a.name.localeCompare(b.name));
  return (
    <>
      <HouseSummary dashboard={dashboard} settings={settings} />
      <section className="ll-block" aria-labelledby="lights-title">
        <SectionHead title="Lights" count={lights.length} id="lights-title">
          <button className="lv-button lv-button-primary" type="button" onClick={() => setAdding(true)}>
            <CirclePlus size={17} />
            Add lights
          </button>
        </SectionHead>
        {lights.length ? (
          <div className="ll-grid">
            {lights.map((light) => (
              <LightCard light={light} dashboard={dashboard} settings={settings} key={light.id} />
            ))}
          </div>
        ) : (
          <p className="lv-alert">No lights yet. Use Add lights to scan your network.</p>
        )}
      </section>
      {adding && <AddLights dashboard={dashboard} settings={settings} onClose={() => setAdding(false)} />}
    </>
  );
}
