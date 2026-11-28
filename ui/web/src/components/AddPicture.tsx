import { ImagePlus, RotateCcw } from "lucide-react";
import { useRef, useState } from "react";

import { lumia, useAct, type Settings } from "../api";
import { useToast } from "./Toasts";

/** Fit a chosen picture to the cards' 3:2 shape, as a JPEG data URL. */
export async function fittedPicture(file: File, [width, height]: [number, number], quality = 0.88): Promise<string> {
  let bitmap: ImageBitmap;
  try {
    bitmap = await createImageBitmap(file);
  } catch {
    throw new Error("Choose a valid JPG, PNG, or WebP picture.");
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const scale = Math.max(width / bitmap.width, height / bitmap.height);
  const [drawnWidth, drawnHeight] = [bitmap.width * scale, bitmap.height * scale];
  canvas.getContext("2d")!.drawImage(bitmap, (width - drawnWidth) / 2, (height - drawnHeight) / 2, drawnWidth, drawnHeight);
  bitmap.close();
  return canvas.toDataURL("image/jpeg", quality);
}

type Props = { kind: "light" | "room" | "group"; id: number; name: string; settings: Settings; own: boolean; className: string };

/** "Add image" (or "Change image"): a picture from this device, stored in Luna Visia and shown on the card. */
export function AddPicture({ kind, id, name, settings, own, className }: Props) {
  const act = useAct();
  const toast = useToast();
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const store = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    toast(`Storing the picture of ${name} in Luna Visia…`);
    const stored = await act(
      async () => lumia.storePicture(kind, id, await fittedPicture(file, settings.picture_size)),
      `The picture of ${name} could not be stored in Luna Visia.`,
    );
    setBusy(false);
    if (stored) toast(`${name} shows your picture, saved in Luna Visia`);
  };

  return (
    <>
      <button className={className} type="button" disabled={busy} aria-busy={busy}
        aria-label={`${own ? "Change" : "Add"} the picture of ${name}`} title="Stored in Luna Visia" onClick={() => input.current?.click()}>
        <ImagePlus size={15} />
        {busy ? "Storing…" : own ? "Change image" : "Add image"}
      </button>
      <input ref={input} type="file" hidden accept={settings.picture_types.map((type) => `.${type}`).join(",")}
        onChange={(event) => { store(event.target.files?.[0]); event.target.value = ""; }} />
    </>
  );
}

/** "Default image": drops the card's own picture, back to the one Lumia picks from its name. */
export function RestorePicture({ kind, id, name, className }: Pick<Props, "kind" | "id" | "name" | "className">) {
  const act = useAct();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const restore = async () => {
    setBusy(true);
    const done = await act(() => lumia.restorePicture(kind, id), `The default picture of ${name} could not be restored.`);
    setBusy(false);
    if (done) toast(`${name} shows its default picture again`);
  };
  return (
    <button className={className} type="button" disabled={busy} aria-busy={busy}
      aria-label={`Restore the default picture of ${name}`} title="Back to the picture Lumia picks from its name" onClick={restore}>
      <RotateCcw size={15} />
      {busy ? "Restoring…" : "Default image"}
    </button>
  );
}

/** A card's picture buttons, over the top right of its picture: add or change it, and restore the default. */
export function PictureActions(props: Omit<Props, "className">) {
  return (
    <div className="ll-picture-actions">
      {props.own && <RestorePicture {...props} className="ll-picture-button" />}
      <AddPicture {...props} className="ll-picture-button" />
    </div>
  );
}
