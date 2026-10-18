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
- Set brightness, RGB color, and white color temperature
- Save and apply solid color/temperature schemes and animated sequence schemes
- Organize lights into exclusive rooms or reusable groups
- Keep each light in at most one room while allowing it in multiple groups
- Display room photography from Luna Visia on each light card
- Create recurring on/off or color-scheme schedules and alarms in Asia/Kolkata
- Control lights through the dashboard, REST endpoints, or MCP tools

The initial `Living room light` is seeded at `192.168.1.8`. Lumia sends commands
directly over the local network; no cloud account or light credential is stored.
The discovery scan is user-triggered and sends a WiZ `getPilot` request to each
address on `192.168.1.1–254`. This works across Docker's bridge while accepting
only valid WiZ replies; it does not probe unrelated TCP services or
automatically save found devices.

## Schemes

A scheme is either **solid** (one RGB color or one white temperature, at a
brightness) or a **sequence**: 2–24 steps, each a color or temperature with a
brightness, a hold time, and a **transition** that fades into it from the
previous step. Sequences play once or loop. Transitions are reusable presets
with a fade duration (0–600 s) and a curve (linear, ease-in, ease-out,
ease-in-out).

WiZ bulbs only accept static states, so the backend plays sequences itself
(`mcp/app/playback.py`), sending interpolated frames about 8 times a second.
Changing a light manually or applying another scheme stops its sequence.

Built-in presets (refreshed on startup; they can't be edited or deleted):

- Solid: Focus, Daylight, Reading, Bedtime, Warm evening, Night light
- Sequence: Pulse, Candle light, Fireplace, Party, Ocean, Sunrise (plays once)
- Transitions: Instant, Flicker, Quick fade, Smooth, Slow fade, Long fade

MCP tools: `list_schemes`, `create_solid_scheme`, `create_sequence_scheme`,
`create_transition`, `activate_scene`, and `stop_scene`.

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

It also exposes `create_room` for exclusive room membership and `create_group`
for reusable, overlapping light groups.

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

Favicon and icons: <http://127.0.0.1:18002/favicon.ico> and
`/icons/icon-{48,96,192,512}.png`; the 48 and 96 px icons are also embedded in
the MCP `initialize` server info so connector clients such as Claude can show
them (`mcp/app/branding.py`, assets in `mcp/app/assets/`).

For source synchronization, run Compose Watch in the foreground:

```bash
docker compose -f docker-compose.yaml watch --no-up
```

## Architecture

Backend (`mcp/app`), layered so transports never touch SQL:

- `main.py` – `LunaLumiaApplication` composes every dependency and starts the server
- `http_routes.py` / `mcp_tools.py` – REST routes and MCP tools; both call only the `LumiaService` facade
- `services.py` – use cases: `LightService`, `CollectionService` (rooms/groups), `BackgroundImageService`, `LightControlService`, `SceneService`, `ScheduleService`
- `repositories.py` – one PostgreSQL repository per aggregate
- `room_images.py` – pure room-detection and image-selection rules
- `devices.py` – WiZ protocol adapter and LAN discovery
- `workers.py` – schedule runner and light-status poller threads
- `models.py`, `config.py`, `errors.py`, `database.py` – validation, settings, domain errors, schema

UI (`ui`): `app.py` composes the page; `services/api.py` is the backend client;
`domain/dashboard.py` wraps the API payload; `views/` holds one class per tab
(`LightsTab`, `RoomsTab`, `SchemesTab`, `SchedulesTab`) plus shared components
in `views/shared.py`. Widget keys are
part of the styling contract in `styles.py`, so keep them stable.

Run backend tests with `docker compose exec mcp python -m unittest discover -s tests`.

## Project structure

Luna Vita, Luna Lumia, and Luna Visia share this layout:

```text
.
├── docker-compose.yaml     # services, private network, and Compose Watch rules
├── README.md
├── UI_STYLE_GUIDE.md       # shared Luna visual reference
├── docs/assets/            # README screenshots
├── mcp/                    # FastMCP server: MCP tools plus UI-facing HTTP routes
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app/                # main.py composition root, config, database, models,
│   │                       # repositories, services, mcp_tools, http_routes,
│   │                       # and the app's own domain modules
│   ├── scripts/            # one-off maintenance scripts, when needed
│   └── tests/              # python -m unittest discover -s tests
└── ui/                     # Streamlit interface
    ├── Dockerfile
    ├── requirements.txt
    ├── .streamlit/         # Streamlit theme and server settings
    ├── assets/             # logos
    ├── app.py              # entry point and page composition
    ├── config.py           # environment-backed settings
    ├── styles.py           # shared dark theme
    ├── services/           # backend API client, caching, and session state
    ├── domain/             # Streamlit-free logic and view models, when the app has any
    ├── views/              # Streamlit rendering: tabs, sections, dialogs, shared widgets
    └── tests/              # UI logic tests, when the app has any
```

Dependencies point one way: `views/` uses `services/` and `domain/`, and `domain/`
imports neither Streamlit nor the API client, so it can be tested on its own.

## Logo

The Lumia logo is stored at `ui/assets/lunalumia_logo.png` and is used in both
the branded header and the browser tab.

## Notes

- Device protocol currently targets WiZ lights through `pywizlight`. If the light
  at `192.168.1.8` is another brand, add its protocol adapter before sending
  commands.
- All application services use unique `luna-lumia-*` network aliases.
- PostgreSQL data is kept in Lumia's own named Compose volume.
