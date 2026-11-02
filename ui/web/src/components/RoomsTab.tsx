import { Circle, DoorOpen, Palette, Plus, Square, Timer, Trash2, Users, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { lumia, useAct, useControl, type Collection, type Dashboard, type Settings } from "../api";
import { accent, addableLights, imageStyle, isValidName } from "../dashboard";
import { messageOf } from "../lib";
import { LightChoice, NameEditor, Toggle } from "./controls";
import { Dialog } from "./Dialog";
import { useToast } from "./Toasts";

type TabProps = { dashboard: Dashboard; settings: Settings };

function SchemePicker({ collection, dashboard, onClose }: { collection: Collection; dashboard: Dashboard; onClose: () => void }) {
  const act = useAct();
  const toast = useToast();
  const target = { type: "group", id: collection.id };
  const playingIds = new Set(collection.light_ids.map((id) => dashboard.playing[id]));
  const playing = dashboard.scenes.find((scheme) => playingIds.has(scheme.id));

  const apply = (id: number) =>
    act(async () => {
      const result = await lumia.applyScheme(id, target);
      const count = result?.light_ids?.length ?? 0;
      toast(`${result?.scene ?? "Scheme"} applied to ${collection.name} (${count} light${count === 1 ? "" : "s"})`);
      onClose();
    });

  return (
    <Dialog title={`Apply a scheme to ${collection.name}`} onClose={onClose}>
      {playing && (
        <button
          className="lv-button lv-button-wide ll-stop"
          type="button"
          onClick={() => act(() => lumia.stopSchemes(target)).then(onClose)}
        >
          <Square size={15} />
          Stop {playing.name}
        </button>
      )}
      {(
        [
          ["solid", "Solid", Circle],
          ["sequence", "Sequence", Timer],
        ] as const
      ).map(([kind, heading, Icon]) => {
        const schemes = dashboard.scenes.filter((scheme) => scheme.kind === kind);
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
    </Dialog>
  );
}

function AddLights({ collection, dashboard, onClose }: { collection: Collection; dashboard: Dashboard; onClose: () => void }) {
  const [chosen, setChosen] = useState<number[]>([]);
  const act = useAct();
  const addable = addableLights(dashboard, collection);
  return (
    <Dialog title={`Add lights to ${collection.name}`} onClose={onClose}>
      {addable.length ? (
        <div className="lv-form">
          <LightChoice lights={addable} chosen={chosen} onChange={setChosen} />
          <button
            className="lv-button"
            type="button"
            disabled={!chosen.length}
            onClick={() => act(() => lumia.addLights(collection.kind, collection.id, chosen)).then(onClose)}
          >
            Add
          </button>
        </div>
      ) : (
        <p className="lv-caption">
          {collection.kind === "group" ? "All lights are already in this group." : "No unassigned lights available."}
        </p>
      )}
    </Dialog>
  );
}

function CollectionCard({ collection, dashboard, settings }: TabProps & { collection: Collection }) {
  const act = useAct();
  const control = useControl();
  const [dialog, setDialog] = useState<"schemes" | "lights" | null>(null);
  const { id, kind } = collection;
  const members = dashboard.lights.filter((light) => collection.light_ids.includes(light.id));
  const isOn = members.length > 0 && members.every((light) => light.is_on);
  const playingIds = new Set(members.map((light) => dashboard.playing[light.id]));
  const playing = dashboard.scenes.find((scheme) => playingIds.has(scheme.id));

  return (
    <article className="ll-room">
      <div className="ll-room-image" style={imageStyle(collection.effective_image_url)}>
        {!collection.effective_image_url && <DoorOpen size={32} />}
        {isOn && <span className="ll-power-on" aria-label="Room on" />}
      </div>
      <div className="ll-room-body">
        <div className="ll-room-header">
          <NameEditor
            name={collection.name}
            entity={kind === "room" ? "Room" : "Group"}
            maxChars={settings.name_max_chars}
            onRename={(name) => act(() => lumia.update(`${kind}s`, id, { name }))}
          />
          <Toggle
            label="On"
            checked={isOn}
            disabled={!members.length}
            onChange={(on) => control({ type: "group", id }, { on }, (light) => collection.light_ids.includes(light.id), "Could not update this room.")}
          />
          <div className="ll-room-actions">
            <button
              className="lv-button ll-small"
              type="button"
              aria-label={`Apply a scheme to ${collection.name}`}
              disabled={!members.length}
              onClick={() => setDialog("schemes")}
            >
              {playing ? <Timer size={16} /> : <Palette size={16} />}
              {playing?.name}
            </button>
            <button className="lv-button ll-small" type="button" aria-label={`Delete ${collection.name}`} onClick={() => act(() => lumia.delete(`${kind}s`, id))}>
              <Trash2 size={16} />
            </button>
          </div>
        </div>
        <div className="ll-pills">
          {!members.length && <span className="lv-caption ll-no-lights">No lights</span>}
          {members.map((light, index) => (
            <span className="ll-pill" style={accent(index)} key={light.id}>
              <span className="ll-orb-label">
                <i className={light.is_on ? "ll-orb ll-orb-on" : "ll-orb"} />
                {light.is_on ? "On" : "Off"}
              </span>
              <span className="ll-orb-label">
                <i className={light.reachable === true ? "ll-orb ll-orb-online" : "ll-orb"} />
                {light.reachable === true ? "Online" : "Offline"}
              </span>
              <strong>{light.name}</strong>
              <button type="button" aria-label={`Remove ${light.name} from ${collection.name}`} onClick={() => act(() => lumia.removeLight(kind, id, light.id), `Could not remove this light from the ${kind}.`)}>
                <X size={14} />
              </button>
            </span>
          ))}
          <button className="lv-button ll-small" type="button" aria-label={`Add lights to ${collection.name}`} onClick={() => setDialog("lights")}>
            <Plus size={16} />
          </button>
        </div>
      </div>
      {dialog === "schemes" && <SchemePicker collection={collection} dashboard={dashboard} onClose={() => setDialog(null)} />}
      {dialog === "lights" && <AddLights collection={collection} dashboard={dashboard} onClose={() => setDialog(null)} />}
    </article>
  );
}

function CreateForm({ kind, dashboard, settings }: TabProps & { kind: "room" | "group" }) {
  const [name, setName] = useState("");
  const [chosen, setChosen] = useState<number[]>([]);
  const [error, setError] = useState("");
  const act = useAct();
  const isRoom = kind === "room";
  const label = isRoom ? "Room" : "Group";
  const taken = new Set(dashboard.rooms.flatMap((room) => room.light_ids));
  const options = isRoom ? dashboard.lights.filter((light) => !taken.has(light.id)) : dashboard.lights;

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!name.trim()) return setError(`Enter a ${kind} name.`);
    if (!isValidName(name)) return setError(`${label} name may contain only letters, numbers, and spaces.`);
    if (!chosen.length) return setError("Select at least one light.");
    setError("");
    try {
      await lumia.create(`${kind}s`, { name, light_ids: chosen });
      setName("");
      setChosen([]);
    } catch (failure) {
      setError(messageOf(failure, `The ${kind} could not be created.`));
    }
    await act(async () => {});
  };

  return (
    <form className="lv-panel lv-form" onSubmit={submit}>
      <label className="lv-field">
        {label} name
        <input
          className="lv-input"
          placeholder={isRoom ? "Bedroom" : "Downstairs"}
          maxLength={settings.name_max_chars}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </label>
      <div className="lv-field">
        Lights
        <LightChoice lights={options} chosen={chosen} onChange={setChosen} />
        {!isRoom && <span>Lights can belong to multiple groups.</span>}
        {isRoom && !options.length && <span>All lights are already assigned to rooms.</span>}
      </div>
      {error && <p className="lv-alert lv-alert-error">{error}</p>}
      <button className="lv-button" type="submit">
        Create {kind}
      </button>
    </form>
  );
}

export function RoomsTab({ dashboard, settings }: TabProps) {
  const [kind, setKind] = useState<"room" | "group">("room");
  return (
    <>
      {[...dashboard.rooms, ...dashboard.groups].map((collection) => (
        <CollectionCard collection={collection} dashboard={dashboard} settings={settings} key={`${collection.kind}-${collection.id}`} />
      ))}
      <div className="lv-tabs" role="tablist">
        <button className={kind === "room" ? "lv-tab lv-tab-active" : "lv-tab"} type="button" role="tab" aria-selected={kind === "room"} onClick={() => setKind("room")}>
          <DoorOpen size={15} /> Room
        </button>
        <button className={kind === "group" ? "lv-tab lv-tab-active" : "lv-tab"} type="button" role="tab" aria-selected={kind === "group"} onClick={() => setKind("group")}>
          <Users size={15} /> Group
        </button>
      </div>
      <CreateForm kind={kind} dashboard={dashboard} settings={settings} key={kind} />
    </>
  );
}
