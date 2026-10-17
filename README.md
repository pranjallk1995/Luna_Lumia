# Luna Lumia

> **Work in progress:** Luna Lumia is a local-first and desktop first nutrition and body-measurement tracker under active development.

## Control, Automate and Manage your Smart Lights LLMs

Luna Lumia is the Luna-family smart-light controller. It uses the same
Streamlit + Python/FastMCP + PostgreSQL structure and shared visual system as
Luna Visia and Luna Vita.

## Features

- Add and remove WiZ-compatible lights by local IPv4 address
- Scan the `192.168.1.x` LAN for WiZ lights and add discovered devices from the UI
- Store each discovered light's normalized MAC address with its device record
- Turn one light, a group, or every light on and off
- Set brightness and RGB color
- Save and apply reusable color schemes
- Organize lights into groups
- Display room photography from Luna Visia on each light card
- Create recurring on/off or color-scheme schedules and alarms in Asia/Kolkata
- Control lights through the dashboard, REST endpoints, or MCP tools

The initial `Living room light` is seeded at `192.168.1.8`. Lumia sends commands
directly over the local network; no cloud account or light credential is stored.
The discovery scan is user-triggered and sends a WiZ `getPilot` request to each
address on `192.168.1.1–254`. This works across Docker's bridge while accepting
only valid WiZ replies; it does not probe unrelated TCP services or
automatically save found devices.

## Room images

Light-card backgrounds use immutable Luna Visia public image URLs. Lumia maps
common room words in each light name (such as `Bathroom`, `Kitchen`, `Office`,
or `Balcony`) to the matching stored room image and uses the living-room image
as a fallback for unmatched rooms. A light-specific URL override takes priority
over the room image.

The MCP server exposes these image-management tools:

- `list_room_images`
- `update_room_image`
- `set_light_background_image`
- `clear_light_background_image`

Only `http://` and `https://` image URLs are accepted. When
`set_light_background_image` is called without an image URL, Lumia infers the
room from the optional `room_name` argument or the light name, and selects the
matching configured image while preserving the available image-source scheme.
Use `clear_light_background_image` to remove the stored override and return to
dynamic room-image resolution.

## Run

The shared Luna Visia network must already exist (`luna_visia_lunavisia_network`).

```bash
docker compose -f docker-compose.yaml up --build
```

Open `http://127.0.0.1:18503`. The MCP endpoint is
`http://127.0.0.1:18002/mcp`.

For source synchronization, run Compose Watch in the foreground:

```bash
docker compose -f docker-compose.yaml watch --no-up
```

## Logo

The Lumia logo is stored at `ui/assets/lunalumia_logo.png` and is used in both
the branded header and the browser tab.

## Notes

- Device protocol currently targets WiZ lights through `pywizlight`. If the light
  at `192.168.1.8` is another brand, add its protocol adapter before sending
  commands.
- All application services use unique `luna-lumia-*` network aliases.
- PostgreSQL data is kept in Lumia's own named Compose volume.
