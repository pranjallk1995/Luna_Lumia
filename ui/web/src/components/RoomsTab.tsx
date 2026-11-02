import { Circle, ListChecks, Play, Plus, Square, Sun, Timer, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { lumia, useAct, useControl, type Collection, type Dashboard, type Settings } from "../api";
import { imageStyle, isValidName, lightColor, lightState, roomOf } from "../dashboard";
import { messageOf } from "../lib";
import { Bulb, LightChoice, NameEditor, SectionHead, Slider, Toggle } from "./controls";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

function SchemePicker({ collection, dashboard, onClose }: { collection: Collection; dashboard: Dashboard; onClose: () => void }) {
  const act = useAct();
  const toast = useToast();
  const target = { type: "group", id: collection.id };

  const apply = (id: number) =>
    act(async () => {
      const result = await lumia.applyScheme(id, target);
      const count = result?.light_ids?.length ?? 0;
      toast(`${result?.scene ?? "Scheme"} applied to ${collection.name} (${count} light${count === 1 ? "" : "s"})`);
      onClose();
    });

  // Weather and music schemes are meant for their automations; they stay on the Schemes tab.
  const everyday = dashboard.scenes.filter((scheme) => !scheme.weather_slots?.length && !scheme.music_moods?.length);
  return (
    <Dialog title={`Apply a scheme to ${collection.name}`} onClose={onClose}>
      {(
        [
          ["solid", "Solid", Circle],
          ["sequence", "Sequence", Timer],
        ] as const
      ).map(([kind, heading, Icon]) => {
        const schemes = everyday.filter((scheme) => scheme.kind === kind);
        return (
          schemes.length > 0 && (
            <section key={kind}>
              <h3 className="ll-heading">{heading}</h3>
              <div className="ll-scheme-buttons">
                {schemes.map((scheme) => (
                  <button className="lv-button" type="button" key={scheme.id} title={scheme.name} onClick={() => apply(scheme.id)}>
                    <Icon size={15} />
                    <span>{scheme.name}</span>
                  </button>
                ))}
              </div>
            </section>
          )
        );
      })}
      <p className="lv-caption">Weather and Music schemes are on the Schemes tab.</p>
    </Dialog>
  );
}

/** Choose which lights belong; a room cannot take a light that is already in another room. */
function EditLights({ collection, dashboard, onClose }: { collection: Collection; dashboard: Dashboard; onClose: () => void }) {
  const act = useAct();
  const [chosen, setChosen] = useState(collection.light_ids);
  const available = dashboard.lights.filter((light) => {
    const room = roomOf(dashboard, light.id);
    return collection.kind === "group" || !room || room.id === collection.id;
  });
  const taken = dashboard.lights.filter((light) => !available.includes(light));

  const save = () =>
    act(async () => {
      const added = chosen.filter((id) => !collection.light_ids.includes(id));
      const removed = collection.light_ids.filter((id) => !chosen.includes(id));
      if (added.length) await lumia.addLights(collection.kind, collection.id, added);
      for (const id of removed) await lumia.removeLight(collection.kind, collection.id, id);
    }, `Could not update the lights in ${collection.name}.`).then(onClose);

  return (
    <Dialog title={`Lights in ${collection.name}`} onClose={onClose}>
      <div className="lv-form">
        <LightChoice lights={available} chosen={chosen} onChange={setChosen} />
        {taken.length > 0 && <p className="lv-caption">Already in other rooms: {taken.map((light) => light.name).join(", ")}.</p>}
        <div className="lv-confirm-actions">
          <button className="lv-button" type="button" onClick={onClose}>
            Cancel
          </button>
          <button className="lv-button lv-button-primary" type="button" onClick={save}>
            Save
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function CollectionCard({ collection, dashboard, settings }: TabProps & { collection: Collection }) {
  const act = useAct();
  const control = useControl();
  const toast = useToast();
  const [dialog, setDialog] = useState<"schemes" | "lights" | null>(null);
  const { id, kind } = collection;
  const members = dashboard.lights.filter((light) => collection.light_ids.includes(light.id));
  const live = members.filter((light) => lightState(light) !== "offline");
  const lit = live.filter((light) => light.is_on);
  const allOn = live.length > 0 && live.every((light) => light.is_on);
  const playingIds = new Set(members.map((light) => dashboard.playing[light.id]));
  const playing = dashboard.scenes.find((scheme) => playingIds.has(scheme.id));
  const target = { type: "group", id };
  const inside = (light: { id: number }) => collection.light_ids.includes(light.id);
  const brightness = lit.length ? Math.round(lit.reduce((sum, light) => sum + light.brightness, 0) / lit.length) : 100;
  const colors = lit.map(lightColor);
  // A photo when the room has one; otherwise the colors of its lit lights.
  const band = collection.effective_image_url
    ? imageStyle(collection.effective_image_url)
    : { background: colors.length > 1 ? `linear-gradient(90deg, ${colors.map((color) => `${color}66`).join(",")})` : colors.length ? `linear-gradient(135deg, ${colors[0]}66, ${colors[0]}22)` : undefined };

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
    <article className="ll-panel ll-collection">
      <div className="ll-band" style={band}>
        <div>
          <NameEditor name={collection.name} entity={kind === "room" ? "Room" : "Group"} maxChars={settings.name_max_chars} onRename={(name) => act(() => lumia.update(`${kind}s`, id, { name }))} />
          <span>
            {lit.length} of {members.length} on{members.length > live.length ? ` · ${members.length - live.length} offline` : ""}
          </span>
        </div>
        <Toggle label={`${collection.name} on`} hideLabel checked={allOn} disabled={!live.length} onChange={(on) => control(target, { on }, inside, `Could not update ${collection.name}.`)} />
      </div>
      <div className="ll-collection-body">
        <Slider label={`${collection.name} brightness`} icon={Sun} min={1} max={100} unit="%" value={brightness} disabled={!lit.length} onCommit={(value) => control(target, { brightness: value }, (light) => inside(light) && light.is_on, `Could not update ${collection.name}.`)} />
        {members.length ? (
          <ul className="ll-members">
            {members.map((light) => {
              const state = lightState(light);
              return (
                <li key={light.id}>
                  <Bulb color={lightColor(light)} state={state} small />
                  <span>{light.name}</span>
                  <span>{state === "on" ? `${light.brightness}%` : state}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="lv-caption">No lights yet.</p>
        )}
        {playing && <span className="ll-tag ll-tag-playing">Playing {playing.name}</span>}
        <div className="ll-collection-actions">
          {playing ? (
            <button className="lv-button ll-small-button ll-grow" type="button" onClick={() => act(() => lumia.stopSchemes(target))}>
              <Square size={15} />
              Stop
            </button>
          ) : (
            <button className="lv-button ll-small-button ll-grow" type="button" disabled={!live.length} onClick={() => setDialog("schemes")}>
              <Play size={15} />
              Apply a scheme
            </button>
          )}
          <button className="lv-icon-button" type="button" aria-label={`Edit lights in ${collection.name}`} title="Edit lights" onClick={() => setDialog("lights")}>
            <ListChecks size={16} />
          </button>
          <button className="lv-icon-button" type="button" aria-label={`Delete ${collection.name}`} title="Delete" onClick={remove}>
            <Trash2 size={16} />
          </button>
        </div>
      </div>
      {dialog === "schemes" && <SchemePicker collection={collection} dashboard={dashboard} onClose={() => setDialog(null)} />}
      {dialog === "lights" && <EditLights collection={collection} dashboard={dashboard} onClose={() => setDialog(null)} />}
    </article>
  );
}

function CreateDialog({ kind, dashboard, settings, onClose }: TabProps & { kind: "room" | "group"; onClose: () => void }) {
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<number[]>([]);
  const [error, setError] = useState("");
  const act = useAct();
  const isRoom = kind === "room";
  const label = isRoom ? "Room" : "Group";
  const options = isRoom ? dashboard.lights.filter((light) => !roomOf(dashboard, light.id)) : dashboard.lights;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError(`Enter a ${kind} name.`);
    if (!isValidName(name)) return setError(`${label} name may contain only letters, numbers, and spaces.`);
    if (!chosen.length) return setError("Select at least one light.");
    setError("");
    await act(async () => {
      try {
        await lumia.create(`${kind}s`, { name, light_ids: chosen });
        onClose();
      } catch (failure) {
        setError(messageOf(failure, `The ${kind} could not be created.`));
      }
    });
  };

  return (
    <Dialog title={`New ${kind}`} onClose={onClose}>
      <form className="lv-form" onSubmit={submit}>
        <label className="lv-field">
          {label} name
          <input className="lv-input" placeholder={isRoom ? "Bedroom" : "Downstairs"} maxLength={settings.name_max_chars} value={name} autoFocus onChange={(event) => setName(event.target.value)} />
        </label>
        <div className="lv-field">
          Lights
          <LightChoice lights={options} chosen={chosen} onChange={setChosen} />
          {!isRoom && <span>Lights can belong to several groups.</span>}
        </div>
        {error && <p className="lv-alert lv-alert-error">{error}</p>}
        <button className="lv-button lv-button-primary" type="submit">
          Create {kind}
        </button>
      </form>
    </Dialog>
  );
}

export function RoomsTab({ dashboard, settings }: TabProps) {
  const [creating, setCreating] = useState<"room" | "group" | null>(null);
  const free = dashboard.lights.filter((light) => !roomOf(dashboard, light.id));
  return (
    <>
      <section className="ll-block" aria-labelledby="rooms-title">
        <SectionHead title="Rooms" count={dashboard.rooms.length} id="rooms-title">
          {!free.length && <span className="lv-caption ll-inline">Every light is already in a room</span>}
          <button className="lv-button lv-button-primary" type="button" disabled={!free.length} onClick={() => setCreating("room")}>
            <Plus size={17} />
            New room
          </button>
        </SectionHead>
        <div className="ll-grid">
          {dashboard.rooms.map((room) => (
            <CollectionCard collection={room} dashboard={dashboard} settings={settings} key={`room-${room.id}`} />
          ))}
        </div>
      </section>
      <section className="ll-block" aria-labelledby="groups-title">
        <SectionHead title="Groups" count={dashboard.groups.length} id="groups-title">
          <span className="lv-caption ll-inline">A light can be in several groups</span>
          <button className="lv-button" type="button" disabled={!dashboard.lights.length} onClick={() => setCreating("group")}>
            <Plus size={17} />
            New group
          </button>
        </SectionHead>
        {dashboard.groups.length ? (
          <div className="ll-grid">
            {dashboard.groups.map((group) => (
              <CollectionCard collection={group} dashboard={dashboard} settings={settings} key={`group-${group.id}`} />
            ))}
          </div>
        ) : (
          <p className="lv-caption">No groups yet. A group gathers lights from different rooms, such as everything for a movie.</p>
        )}
      </section>
      {creating && <CreateDialog kind={creating} dashboard={dashboard} settings={settings} onClose={() => setCreating(null)} />}
    </>
  );
}
