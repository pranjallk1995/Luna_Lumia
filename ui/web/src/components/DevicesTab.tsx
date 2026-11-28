/** Devices: everything that sets Lumia up, kept off the everyday screens. Adding and finding lights, rooms and groups with their pictures, and every light in one table. */

import { CirclePlus, Cpu, Lightbulb, ListChecks, MapPin, Plus, Radar, Trash2 } from "lucide-react";
import { useState } from "react";

import { lumia, useAct, type Collection, type Dashboard, type Light, type Settings } from "../api";
import { hasOwnPicture, imageStyle, lightState, roomOf } from "../dashboard";
import { PictureActions } from "./AddPicture";
import { NameEditor, SectionHead } from "./controls";
import { AddLights, DeleteLight, FindMoved, lastSeen } from "./LightsTab";
import { CreateDialog, EditLights } from "./RoomsTab";
import { LocationDialog } from "./SchedulesTab";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

const plural = (count: number, word: string) => `${count} ${word}${count === 1 ? "" : "s"}`;

/** What a light is and where it answers: a WiZ bulb, or a PC device through iCUE or OpenRGB. */
function lightKind(light: Light): [string, string] {
  if (light.protocol === "icue") return [`iCUE · ${light.device ?? "device"}`, light.ip_address];
  if (light.protocol === "openrgb" || light.device) {
    const part = light.zone ? ` · zone ${light.zone}` : light.leds ? ` · LEDs ${light.leds}` : "";
    return [`OpenRGB · ${light.device ?? "device"}${part}`, light.ip_address];
  }
  return ["WiZ bulb", `${light.ip_address}${light.mac_address ? ` · ${light.mac_address}` : ""}`];
}

function PlaceCard({ collection, dashboard, settings }: TabProps & { collection: Collection }) {
  const act = useAct();
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const { id, kind } = collection;
  const own = hasOwnPicture(dashboard, collection.effective_image_url);

  const remove = async () => {
    const removed = await act(() => lumia.delete(`${kind}s`, id), `Could not delete ${collection.name}.`);
    // Undo re-creates it with the same lights; the backend gives it a new id.
    if (removed)
      toast(`${collection.name} deleted`, {
        label: "Undo",
        run: () => act(() => lumia.create(`${kind}s`, { name: collection.name, light_ids: collection.light_ids }), `Could not restore ${collection.name}.`),
      });
  };

  return (
    <article className="ll-place">
      <div className="ll-place-picture" style={imageStyle(collection.effective_image_url)}>
        <span className="ll-place-note">{own ? "Your picture" : collection.effective_image_url ? "Default picture" : "No picture"}</span>
        <PictureActions kind={kind} id={id} name={collection.name} settings={settings} own={own} />
      </div>
      <div className="ll-place-body">
        <div className="ll-place-name">
          <NameEditor name={collection.name} entity={kind === "room" ? "Room" : "Group"} maxChars={settings.name_max_chars} onRename={(name) => act(() => lumia.update(`${kind}s`, id, { name }))} />
          <span className="ll-now-label">
            {kind === "room" ? "Room" : "Group"} · {plural(collection.light_ids.length, "light")}
          </span>
        </div>
        <div className="ll-place-actions">
          <button className="lv-button ll-small-button" type="button" onClick={() => setEditing(true)}>
            <ListChecks size={15} />
            Lights
          </button>
          <button className="lv-icon-button" type="button" aria-label={`Delete ${collection.name}`} title="Delete" onClick={remove}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      {editing && <EditLights collection={collection} dashboard={dashboard} onClose={() => setEditing(false)} />}
    </article>
  );
}

function LightRow({ light, dashboard, settings }: TabProps & { light: Light }) {
  const act = useAct();
  const [deleting, setDeleting] = useState(false);
  const room = roomOf(dashboard, light.id);
  const state = lightState(light);
  const own = hasOwnPicture(dashboard, light.effective_image_url);
  const picture = light.effective_image_url ?? room?.effective_image_url;
  const [kind, address] = lightKind(light);
  const seen = lastSeen(light);

  /** A light is in at most one room: leave the old one, then join the new. */
  const move = (roomId: string) =>
    act(async () => {
      if (room) await lumia.removeLight("room", room.id, light.id);
      if (roomId) await lumia.addLights("room", Number(roomId), [light.id]);
    }, `Could not move ${light.name}.`);

  return (
    <tr className={state === "offline" ? "ll-row-offline" : undefined}>
      <td>
        <span className="ll-light-cell">
          <span className="ll-light-thumb" style={imageStyle(picture)} aria-hidden="true" />
          <span className="ll-light-who">
            <NameEditor name={light.name} entity="Light" maxChars={settings.name_max_chars} onRename={(name) => act(() => lumia.renameLight(light.id, name, own))} />
            <span className="ll-now-label">{own ? "Its own picture" : picture ? "Its room's picture" : "No picture"}</span>
          </span>
        </span>
      </td>
      <td>
        <select className="lv-select ll-room-select" aria-label={`Room of ${light.name}`} value={room?.id ?? ""} onChange={(event) => move(event.target.value)}>
          <option value="">No room</option>
          {dashboard.rooms.map((option) => (
            <option value={option.id} key={option.id}>
              {option.name}
            </option>
          ))}
        </select>
      </td>
      <td>
        {kind}
        <span className="ll-now-label ll-block-label">{address}</span>
      </td>
      <td>
        <span className={`ll-status ll-status-${state}`}>
          <span aria-hidden="true" />
          {state === "offline" ? `Offline${seen ? ` · seen ${seen}` : ""}` : state === "on" ? "On" : "Off"}
        </span>
      </td>
      <td>
        <span className="ll-row-actions">
          <PictureActions kind="light" id={light.id} name={light.name} settings={settings} own={own} />
          <button className="lv-icon-button" type="button" aria-label={`Delete ${light.name}`} title="Delete" onClick={() => setDeleting(true)}>
            <Trash2 size={16} />
          </button>
        </span>
        {deleting && <DeleteLight light={light} room={room?.name} onClose={() => setDeleting(false)} />}
      </td>
    </tr>
  );
}

export function DevicesTab({ dashboard, settings }: TabProps) {
  const [adding, setAdding] = useState(false);
  const [creating, setCreating] = useState<"room" | "group" | null>(null);
  const [locating, setLocating] = useState(false);
  const { lights } = dashboard;
  const offline = lights.filter((light) => lightState(light) === "offline").length;
  const pc = lights.filter((light) => light.device);
  const pcSources = [...new Set(pc.map((light) => (light.protocol === "icue" ? "iCUE" : "OpenRGB")))];
  const free = lights.filter((light) => !roomOf(dashboard, light.id));
  const roomName = (light: Light) => roomOf(dashboard, light.id)?.name ?? "￿";
  const sorted = [...lights].sort((a, b) => roomName(a).localeCompare(roomName(b)) || a.name.localeCompare(b.name));
  const places = [...dashboard.rooms, ...dashboard.groups];

  return (
    <>
      <section className="ll-now ll-setup" aria-label="Setup">
        <div className="ll-now-cell">
          <Lightbulb size={20} className="ll-now-icon" aria-hidden="true" />
          <span className="ll-now-text">
            <span className="ll-now-label">Lights</span>
            <strong>
              {lights.length} added{offline ? ` · ${offline} offline` : ""}
            </strong>
          </span>
          <button className="lv-button lv-button-primary ll-small-button" type="button" onClick={() => setAdding(true)}>
            <CirclePlus size={15} />
            Add
          </button>
        </div>
        <div className="ll-now-cell">
          <Radar size={20} className="ll-now-icon" aria-hidden="true" />
          <span className="ll-now-text">
            <span className="ll-now-label">After a router restart</span>
            <strong>Lights at new addresses</strong>
          </span>
          {lights.length > 0 && <FindMoved dashboard={dashboard} settings={settings} />}
        </div>
        <div className="ll-now-cell">
          <Cpu size={20} className="ll-now-icon" aria-hidden="true" />
          <span className="ll-now-text">
            <span className="ll-now-label">PC</span>
            <strong>{pc.length ? `${plural(pc.length, "device")} · ${pcSources.join(", ")}` : "No PC lights"}</strong>
          </span>
          <button className="lv-button ll-small-button" type="button" onClick={() => setAdding(true)}>
            Find
          </button>
        </div>
        <div className="ll-now-cell">
          <MapPin size={20} className="ll-now-icon" aria-hidden="true" />
          <span className="ll-now-text">
            <span className="ll-now-label">Location, for sunrise and weather</span>
            <strong className="ll-truncate">{dashboard.location?.name ?? "Not set"}</strong>
          </span>
          <button className="lv-button ll-small-button" type="button" onClick={() => setLocating(true)}>
            {dashboard.location ? "Change" : "Set"}
          </button>
        </div>
      </section>

      <section className="ll-block" aria-labelledby="places-title">
        <SectionHead title="Rooms and groups" count={places.length} id="places-title">
          <button className="lv-button" type="button" disabled={!free.length} title={free.length ? undefined : "Every light is already in a room"} onClick={() => setCreating("room")}>
            <Plus size={17} />
            New room
          </button>
          <button className="lv-button" type="button" disabled={!lights.length} onClick={() => setCreating("group")}>
            <Plus size={17} />
            New group
          </button>
        </SectionHead>
        {places.length ? (
          <div className="ll-places">
            {places.map((collection) => (
              <PlaceCard collection={collection} dashboard={dashboard} settings={settings} key={collection.id} />
            ))}
          </div>
        ) : (
          <p className="lv-caption">No rooms yet. A room holds the lights in one place; a group gathers lights from several, such as everything for a movie.</p>
        )}
      </section>

      <section className="ll-block" aria-labelledby="device-lights-title">
        <SectionHead title="Lights" count={lights.length} id="device-lights-title" />
        {lights.length ? (
          <div className="lv-table-scroll ll-lights-table">
            <table>
              <thead>
                <tr>
                  <th scope="col">Light</th>
                  <th scope="col">Room</th>
                  <th scope="col">Kind and address</th>
                  <th scope="col">Status</th>
                  <th scope="col">
                    <span className="ll-sr">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((light) => (
                  <LightRow light={light} dashboard={dashboard} settings={settings} key={light.id} />
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="lv-alert">No lights yet. Use Add to scan your network.</p>
        )}
        <p className="lv-caption">A light without its own picture shows its room's. Default image goes back to the picture Lumia picks from the name.</p>
      </section>

      {adding && <AddLights dashboard={dashboard} settings={settings} onClose={() => setAdding(false)} />}
      {creating && <CreateDialog kind={creating} dashboard={dashboard} settings={settings} onClose={() => setCreating(null)} />}
      {locating && <LocationDialog dashboard={dashboard} onClose={() => setLocating(false)} />}
    </>
  );
}
