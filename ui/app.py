"""Luna Lumia smart-light dashboard."""

import base64
from datetime import time
import html
from time import monotonic

import httpx
import streamlit as st
from PIL import Image

from api import LumiaAPI
from config import UIConfig
from styles import LunaStyle


st.set_page_config(
    page_title="Luna Lumia",
    page_icon=Image.open(UIConfig.LOGO_PATH) if UIConfig.LOGO_PATH.is_file() else "💡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
LunaStyle.apply()
api = LumiaAPI(UIConfig.API_URL)


@st.fragment(run_every=10)
def refresh_polled_light_statuses() -> None:
    """Refresh the full dashboard after the backend's ten-second status poll."""
    now = monotonic()
    previous = st.session_state.get("last_light_status_refresh")
    st.session_state.last_light_status_refresh = now
    if previous is not None and now - previous >= 9:
        st.rerun()


refresh_polled_light_statuses()


def call(action, success="Saved"):
    try:
        action()
        st.rerun()
    except httpx.HTTPStatusError as error:
        try:
            message = error.response.json().get("error", str(error))
        except ValueError:
            message = str(error)
        st.error(message)
    except httpx.HTTPError as error:
        st.error(f"Luna Lumia service is unavailable: {error}")


def valid_entity_name(value: str) -> bool:
    cleaned = value.strip()
    return bool(cleaned) and all(
        character.isalnum() or character == " " for character in cleaned
    )


def show_invalid_name_error(entity: str) -> None:
    st.error(f"{entity} name may contain only letters, numbers, and spaces.")


def sync_light_controls(light_id: int) -> None:
    """Send the card's current controls immediately, without a success toast."""
    try:
        api.control(
            "light",
            light_id,
            on=st.session_state[f"on_{light_id}"],
            brightness=st.session_state[f"brightness_{light_id}"],
            color=st.session_state[f"color_{light_id}"],
        )
        st.session_state.pop(f"control_error_{light_id}", None)
    except httpx.HTTPError as error:
        st.session_state[f"control_error_{light_id}"] = str(error)


def sync_room_power(group_id: int, widget_key: str) -> None:
    """Apply a room toggle change immediately without a notification toast."""
    try:
        api.control("group", group_id, on=st.session_state[widget_key])
        st.session_state.pop(f"room_control_error_{group_id}", None)
    except httpx.HTTPError as error:
        st.session_state[f"room_control_error_{group_id}"] = str(error)


def remove_deselected_room_lights(
    group_id: int, widget_key: str, current_light_ids: tuple[int, ...]
) -> None:
    """Remove room memberships deselected from the room's light pills."""
    selected_light_ids = set(st.session_state.get(widget_key) or [])
    removed_light_ids = [
        light_id for light_id in current_light_ids if light_id not in selected_light_ids
    ]
    try:
        for light_id in removed_light_ids:
            api.remove_room_light(group_id, light_id)
        st.session_state.pop(f"room_membership_error_{group_id}", None)
    except httpx.HTTPError as error:
        st.session_state[f"room_membership_error_{group_id}"] = str(error)
    finally:
        generation_key = f"room_light_pills_generation_{group_id}"
        st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1


def rename_light_and_refresh_image(light_id: int, name: str):
    """Rename a light, then infer its background from the updated name."""
    api.update("lights", light_id, {"name": name})
    return api.set_light_background(light_id)


def rename_room_and_refresh_image(room_id: int, name: str):
    """Rename a room and infer a matching background from the updated name."""
    return api.update("groups", room_id, {"name": name})


def select_preset_color(widget_key: str, color: str, light_id: int) -> None:
    st.session_state[widget_key] = color
    sync_light_controls(light_id)


logo_data = (
    base64.b64encode(UIConfig.LOGO_PATH.read_bytes()).decode("ascii")
    if UIConfig.LOGO_PATH.is_file()
    else None
)
try:
    data = api.dashboard()
except httpx.HTTPError as error:
    st.error(f"Luna Lumia service is unavailable: {error}")
    st.stop()

lights = data["lights"]
groups = data["groups"]
scenes = data["scenes"]
schedules = data["schedules"]
room_names_by_light = {light["id"]: [] for light in lights}
for room in groups:
    for light_id in room["light_ids"]:
        if light_id in room_names_by_light:
            room_names_by_light[light_id].append(room["name"])
all_on = bool(lights) and all(light["is_on"] for light in lights)

logo = (
    f'<img class="lv-mark" src="data:image/png;base64,{logo_data}" alt="Luna Lumia logo" />'
    if logo_data
    else '<div class="lv-placeholder">◉</div>'
)
brand_column, power_column = st.columns(
    [5, 4], vertical_alignment="center", gap="medium"
)
with brand_column:
    st.markdown(
        f'<div class="lv-header">{logo}<div><h1 class="lv-title">Luna Lumia</h1><p class="lv-subtitle">Private AI-managed smart lighting</p></div></div>',
        unsafe_allow_html=True,
    )
with power_column:
    if st.button(
        "Turn all off" if all_on else "Turn all on",
        type="primary",
        use_container_width=True,
        icon=":material/power_settings_new:",
        key="header_all_lights_power",
    ):
        call(lambda: api.control("all", on=not all_on), None)

tab_lights, tab_groups, tab_scenes, tab_schedules = st.tabs(
    [
        ":material/lightbulb: Lights",
        ":material/group: Rooms",
        ":material/palette: Schemes",
        ":material/schedule: Schedules",
    ]
)

with tab_lights:
    with st.container(border=True):
        scan_icon, scan_title, scan_action = st.columns(
            [0.55, 4, 1.35], vertical_alignment="center", gap="medium"
        )
        scan_icon.markdown(
            '<div class="find-lights-icon"><span class="material-symbols-rounded">lightbulb</span></div>',
            unsafe_allow_html=True,
        )
        scan_title.markdown(
            '<div class="find-lights-card"><h2>Find lights on your network</h2><p>Scans for WiZ-compatible lights and lists their IP addresses. Nothing is added automatically.</p></div>',
            unsafe_allow_html=True,
        )
        if scan_action.button(
            "Scan for lights",
            icon=":material/radar:",
            use_container_width=True,
            key="scan_for_lights",
        ):
            try:
                with st.spinner("Scanning 192.168.1.x for lights…"):
                    st.session_state.discovered_lights = api.discover("192.168.1.255")
            except httpx.HTTPError as error:
                st.error(f"Network scan failed: {error}")
        discovered = st.session_state.get("discovered_lights")
        if discovered is not None:
            with st.expander(
                f"Found lights ({len(discovered)})",
                expanded=True,
                icon=":material/lightbulb:",
            ):
                st.markdown(
                    '<span class="discovery-results-marker"></span>',
                    unsafe_allow_html=True,
                )
                configured_ips = {light["ip_address"] for light in lights}
                if not discovered:
                    st.info(
                        "No WiZ lights answered the scan. Confirm they are powered on and connected to the 192.168.1.x network."
                    )
                for bulb in discovered:
                    already_added = bulb["ip_address"] in configured_ips
                    bulb_row, add_column = st.columns(
                        [4, 1], vertical_alignment="bottom"
                    )
                    with bulb_row:
                        proposed_name = st.text_input(
                            f'{bulb["ip_address"]} · {bulb.get("mac_address") or "MAC unavailable"}',
                            value=bulb["suggested_name"],
                            disabled=already_added,
                            key=f'discovered_name_{bulb["ip_address"].replace(".", "_")}',
                        )
                    if already_added:
                        add_column.button(
                            "Added",
                            disabled=True,
                            use_container_width=True,
                            key=f'discovered_added_{bulb["ip_address"]}',
                        )
                    elif add_column.button(
                        "Add",
                        use_container_width=True,
                        key=f'discovered_add_{bulb["ip_address"]}',
                    ):
                        call(
                            lambda b=bulb, n=proposed_name: api.create(
                                "lights",
                                {
                                    "name": n,
                                    "ip_address": b["ip_address"],
                                    "protocol": "wiz",
                                    "mac_address": b.get("mac_address"),
                                },
                            ),
                            "Light added",
                        )
    on_count = sum(bool(light.get("is_on")) for light in lights)
    online_count = sum(light.get("reachable") is True for light in lights)
    st.markdown(
        f'<div class="light-stats-row"><div class="light-stat-card"><span class="material-symbols-rounded total">bolt</span><div><strong>{len(lights)}</strong><small>Total lights</small></div></div><div class="light-stat-card"><span class="status-orb on"></span><div><strong>{on_count}</strong><small>On</small></div></div><div class="light-stat-card"><span class="status-orb online"></span><div><strong>{online_count}</strong><small>Online</small></div></div></div>',
        unsafe_allow_html=True,
    )
    for index in range(0, len(lights), 3):
        columns = st.columns(3)
        for column, light in zip(columns, lights[index : index + 3]):
            with column, st.container(border=True):
                mac = light.get("mac_address") or "MAC not discovered"
                image_url = html.escape(
                    light.get("effective_image_url") or "", quote=True
                )
                reachability = (
                    "Online"
                    if light["reachable"]
                    else "Status unknown" if light["reachable"] is None else "Offline"
                )
                hero_style = f"background-image:url('{image_url}')" if image_url else ""
                power_indicator = (
                    '<span class="light-card-power-on" aria-label="Light on">●</span>'
                    if light["is_on"]
                    else ""
                )
                st.markdown(
                    f'<div class="light-card-hero" style="{hero_style}">{power_indicator}<span class="light-card-status {"online" if light["reachable"] else ""}"><i></i>{reachability}</span></div>',
                    unsafe_allow_html=True,
                )
                editing_key = f"editing_name_{light['id']}"
                draft_key = f"name_draft_{light['id']}"
                if st.session_state.get(editing_key, False):
                    with st.container(key=f"edit_name_form_{light['id']}"):
                        with st.form(key=f"name_form_{light['id']}", border=False):
                            name_column, confirm_column = st.columns(
                                [5, 1], vertical_alignment="center"
                            )
                            edited_name = name_column.text_input(
                                "Light name",
                                key=draft_key,
                                label_visibility="collapsed",
                                max_chars=30,
                            )
                            with confirm_column:
                                name_submitted = st.form_submit_button(
                                    ":material/check:",
                                    use_container_width=True,
                                )
                        if name_submitted:
                            if not valid_entity_name(edited_name):
                                show_invalid_name_error("Light")
                            else:
                                st.session_state[editing_key] = False
                                call(
                                    lambda l=light, n=edited_name: rename_light_and_refresh_image(
                                        l["id"], n
                                    ),
                                    None,
                                )
                else:
                    if st.button(
                        light["name"],
                        key=f"edit_name_{'on' if light['is_on'] else 'off'}_{light['id']}",
                    ):
                        st.session_state[editing_key] = True
                        st.session_state[draft_key] = light["name"]
                        st.rerun()
                room_names = room_names_by_light.get(light["id"], [])
                st.markdown(
                    f'<div class="light-meta-row"><span class="light-meta">{light["ip_address"]} · {html.escape(mac)}</span></div>',
                    unsafe_allow_html=True,
                )
                st.toggle(
                    "On",
                    value=light["is_on"],
                    key=f"on_{light['id']}",
                    on_change=sync_light_controls,
                    args=(light["id"],),
                )
                st.slider(
                    ":material/brightness_6: Brightness",
                    1,
                    100,
                    int(light["brightness"]),
                    key=f"brightness_{light['id']}",
                    on_change=sync_light_controls,
                    args=(light["id"],),
                )
                st.markdown(
                    '<div class="light-control-label"><span class="material-symbols-rounded">palette</span><span>Color</span></div>',
                    unsafe_allow_html=True,
                )
                color_key = f"color_{light['id']}"
                if color_key not in st.session_state:
                    st.session_state[color_key] = light["color"]
                color_columns = st.columns(
                    [1.35] + [1] * len(UIConfig.PRESET_COLORS), gap="small"
                )
                color_columns[0].color_picker(
                    "Color",
                    key=color_key,
                    label_visibility="collapsed",
                    on_change=sync_light_controls,
                    args=(light["id"],),
                )
                for preset_index, (preset_column, preset_color) in enumerate(
                    zip(color_columns[1:], UIConfig.PRESET_COLORS)
                ):
                    preset_column.button(
                        "●",
                        key=f"preset_color_{light['id']}_{preset_color[1:]}",
                        help=f"Use {preset_color}",
                        on_click=select_preset_color,
                        args=(color_key, preset_color, light["id"]),
                    )
                if st.session_state.get(f"control_error_{light['id']}"):
                    st.error("Could not update this light.")
                room_column, delete_column = st.columns(
                    [8, 1], vertical_alignment="center"
                )
                if room_names:
                    room_column.markdown(
                        f'<span class="light-room-membership"><span class="material-symbols-rounded">meeting_room</span>{html.escape(", ".join(room_names))}</span>',
                        unsafe_allow_html=True,
                    )
                if delete_column.button(
                    "",
                    icon=":material/delete:",
                    key=f"delete_light_{light['id']}",
                ):
                    call(lambda l=light: api.delete("lights", l["id"]), None)
    with st.expander("Add a light", icon=":material/add_circle:"):
        with st.form("add_light", clear_on_submit=True):
            name = st.text_input("Name", placeholder="Bedroom lamp", max_chars=30)
            ip = st.text_input("IP address", placeholder="192.168.1.20")
            if st.form_submit_button("Add light", use_container_width=True):
                if not valid_entity_name(name):
                    show_invalid_name_error("Light")
                else:
                    call(
                        lambda: api.create(
                            "lights",
                            {"name": name, "ip_address": ip, "protocol": "wiz"},
                        ),
                        "Light added",
                    )

with tab_groups:
    for group in groups:
        with st.container(border=True, key=f"room_card_{group['id']}"):
            group_image_url = group.get("effective_image_url") or ""
            selected = [light for light in lights if light["id"] in group["light_ids"]]
            room_is_on = bool(selected) and all(
                light.get("is_on") for light in selected
            )
            available_for_room = [
                light["id"]
                for light in lights
                if not room_names_by_light[light["id"]]
            ]
            image_column, details_column = st.columns(
                [3.6, 8.4], vertical_alignment="top", gap="medium"
            )
            with image_column, st.container(key=f"room_image_{group['id']}"):
                if group_image_url:
                    st.image(group_image_url, width="stretch")
                else:
                    st.markdown(
                        '<div class="room-image-placeholder"><span class="material-symbols-rounded">meeting_room</span></div>',
                        unsafe_allow_html=True,
                    )
                if room_is_on:
                    st.markdown(
                        '<span class="room-image-power-on" aria-label="Room on"></span>',
                        unsafe_allow_html=True,
                    )
                room_editing_key = f"editing_room_name_{group['id']}"
                room_draft_key = f"room_name_draft_{group['id']}"
                if st.session_state.get(room_editing_key, False):
                    with st.container(key=f"edit_room_name_form_{group['id']}"):
                        with st.form(key=f"room_name_form_{group['id']}", border=False):
                            room_name_column, room_confirm_column = st.columns(
                                [5, 1], vertical_alignment="center"
                            )
                            edited_room_name = room_name_column.text_input(
                                "Room name",
                                key=room_draft_key,
                                label_visibility="collapsed",
                                max_chars=30,
                            )
                            with room_confirm_column:
                                room_name_submitted = st.form_submit_button(
                                    ":material/check:",
                                    use_container_width=True,
                                )
                        if room_name_submitted:
                            if not valid_entity_name(edited_room_name):
                                show_invalid_name_error("Room")
                            else:
                                st.session_state[room_editing_key] = False
                                call(
                                    lambda g=group, n=edited_room_name: rename_room_and_refresh_image(
                                        g["id"], n
                                    ),
                                    None,
                                )
                else:
                    if st.button(
                        group["name"],
                        key=f"edit_room_name_{'on' if room_is_on else 'off'}_{group['id']}",
                    ):
                        st.session_state[room_editing_key] = True
                        st.session_state[room_draft_key] = group["name"]
                        st.rerun()
            with details_column:
                room_power_key = f'room_power_{group["id"]}'
                st.session_state[room_power_key] = room_is_on
                with st.container(
                    key=f"room_header_{group['id']}",
                    horizontal=True,
                    horizontal_alignment="distribute",
                    vertical_alignment="center",
                    gap="small",
                ):
                    st.toggle(
                        "On",
                        key=room_power_key,
                        disabled=not selected,
                        on_change=sync_room_power,
                        args=(group["id"], room_power_key),
                    )
                    if st.button("", icon=":material/delete:", key=f"dg{group['id']}"):
                        call(lambda g=group: api.delete("groups", g["id"]), None)
                if st.session_state.get(f"room_control_error_{group['id']}"):
                    st.error("Could not update this room.")
                with st.container(
                    key=f"room_light_row_{group['id']}",
                    horizontal=True,
                    vertical_alignment="center",
                    gap="small",
                ):
                    if selected:
                        current_light_ids = tuple(light["id"] for light in selected)
                        generation_key = f"room_light_pills_generation_{group['id']}"
                        pills_key = (
                            f"room_light_pills_{group['id']}_"
                            f"{st.session_state.get(generation_key, 0)}"
                        )
                        light_by_id = {light["id"]: light for light in selected}

                        def room_light_label(light_id: int) -> str:
                            return light_by_id[light_id]["name"]

                        status_styles = []
                        for index, light in enumerate(selected, start=1):
                            power_label = "On" if light.get("is_on") else "Off"
                            online_label = (
                                "Online"
                                if light.get("reachable") is True
                                else "Offline"
                            )
                            power_color = "#ffbe55" if light.get("is_on") else "#626a79"
                            power_glow = (
                                "rgba(255,190,85,.72)"
                                if light.get("is_on")
                                else "transparent"
                            )
                            online_color = (
                                "#22c55e"
                                if light.get("reachable") is True
                                else "#626a79"
                            )
                            online_glow = (
                                "rgba(34,197,94,.72)"
                                if light.get("reachable") is True
                                else "transparent"
                            )
                            status_styles.append(
                                f'div[class*="st-key-room_light_row_{group["id"]}"] '
                                f'div[data-testid="stButtonGroup"] button:nth-of-type({index})'
                                "{"
                                f'--room-power-label:"{power_label}";'
                                f'--room-online-label:"{online_label}";'
                                f"--room-power-orb:{power_color};"
                                f"--room-power-glow:{power_glow};"
                                f"--room-online-orb:{online_color};"
                                f"--room-online-glow:{online_glow};"
                                "}"
                            )

                        st.markdown(
                            '<span class="room-light-removable-pills"></span>',
                            unsafe_allow_html=True,
                        )
                        st.html(f"<style>{''.join(status_styles)}</style>")
                        st.pills(
                            "Room lights",
                            options=list(current_light_ids),
                            default=list(current_light_ids),
                            format_func=room_light_label,
                            selection_mode="multi",
                            key=pills_key,
                            on_change=remove_deselected_room_lights,
                            args=(group["id"], pills_key, current_light_ids),
                            label_visibility="collapsed",
                            width="content",
                        )
                    else:
                        st.caption("No lights")
                    if st.session_state.get(f"room_membership_error_{group['id']}"):
                        st.error("Could not remove this light from the room.")
                    with st.popover(":material/add:", width="content"):
                        if available_for_room:
                            with st.form(f"add_room_lights_{group['id']}"):
                                added_light_ids = st.multiselect(
                                    "Lights",
                                    options=available_for_room,
                                    format_func=lambda item: next(
                                        light["name"]
                                        for light in lights
                                        if light["id"] == item
                                    ),
                                )
                                if st.form_submit_button("Add", use_container_width=True):
                                    if not added_light_ids:
                                        st.error("Select at least one light.")
                                    else:
                                        call(
                                            lambda g=group, ids=added_light_ids: api.add_room_lights(
                                                g["id"], ids
                                            ),
                                            None,
                                        )
                        else:
                            st.caption("No unassigned lights available.")
    with st.form("add_group", clear_on_submit=True):
        name = st.text_input(
            "Room/Group name :red[*]", placeholder="Bedroom", max_chars=30
        )
        available_light_ids = [
            light["id"] for light in lights if not room_names_by_light[light["id"]]
        ]
        chosen = st.multiselect(
            "Lights :red[*]",
            options=available_light_ids,
            format_func=lambda item: next(
                light["name"] for light in lights if light["id"] == item
            ),
        )
        if not available_light_ids:
            st.caption("All lights are already assigned to rooms.")
        if st.form_submit_button("Create room", use_container_width=True):
            if not name.strip():
                st.error("Enter a room/group name.")
            elif not valid_entity_name(name):
                show_invalid_name_error("Room/group")
            elif not chosen:
                st.error("Select at least one light.")
            else:
                call(
                    lambda: api.create("groups", {"name": name, "light_ids": chosen}),
                    "Room created",
                )

with tab_scenes:
    if scenes:
        columns = st.columns(3)
        for index, scene in enumerate(scenes):
            with columns[index % 3], st.container(border=True):
                st.markdown(
                    f'<div class="light-name"><span class="swatch" style="background:{scene["color"]}"></span>{html.escape(scene["name"])}</div>',
                    unsafe_allow_html=True,
                )
                st.caption(f'{scene["color"]} · {scene["brightness"]}% brightness')
                a, b = st.columns([3, 1])
                if a.button(
                    "Apply to all", key=f"scene{scene['id']}", use_container_width=True
                ):
                    call(
                        lambda s=scene: api.apply_scene(s["id"]), "Color scheme applied"
                    )
                if b.button("", icon=":material/delete:", key=f"ds{scene['id']}"):
                    call(
                        lambda s=scene: api.delete("scenes", s["id"]),
                        "Color scheme removed",
                    )
    with st.form("add_scene", clear_on_submit=True):
        st.subheader("New color scheme")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name", placeholder="Sunset")
        color = c2.color_picker("Color", "#FF8A5B")
        brightness = c3.slider("Brightness", 1, 100, 70)
        if st.form_submit_button("Save scheme", use_container_width=True):
            call(
                lambda: api.create(
                    "scenes", {"name": name, "color": color, "brightness": brightness}
                ),
                "Color scheme saved",
            )

with tab_schedules:
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    for schedule in schedules:
        with st.container(border=True):
            a, b = st.columns([5, 1])
            a.subheader(schedule["name"])
            days = ", ".join(day_names[i] for i in schedule["weekdays"])
            a.caption(
                f'{schedule["kind"].title()} · {schedule["run_time"][:5]} · {days} · {schedule["action"].title()}'
            )
            if b.button("Remove", key=f"dsch{schedule['id']}"):
                call(
                    lambda s=schedule: api.delete("schedules", s["id"]),
                    "Schedule removed",
                )
    with st.form("add_schedule", clear_on_submit=True):
        st.subheader("New schedule or alarm")
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("Name", placeholder="Wake up")
        kind = c2.selectbox("Type", ["schedule", "alarm"], format_func=str.title)
        run_time = c3.time_input("Time", value=time(7, 0))
        target_labels = (
            {"All lights": ("all", None)}
            | {f'Light · {x["name"]}': ("light", x["id"]) for x in lights}
            | {f'Group · {x["name"]}': ("group", x["id"]) for x in groups}
        )
        c4, c5 = st.columns(2)
        target_label = c4.selectbox("Target", list(target_labels))
        action = c5.selectbox(
            "Action",
            ["on", "off", "scene"],
            format_func=lambda x: "Color scheme" if x == "scene" else x.title(),
        )
        scene_id = None
        if action == "scene":
            scene_id = (
                st.selectbox(
                    "Color scheme",
                    [x["id"] for x in scenes],
                    format_func=lambda item: next(
                        x["name"] for x in scenes if x["id"] == item
                    ),
                )
                if scenes
                else None
            )
        days = st.multiselect(
            "Repeat on",
            range(7),
            default=range(7),
            format_func=lambda item: day_names[item],
        )
        target_type, target_id = target_labels[target_label]
        if st.form_submit_button("Save schedule", use_container_width=True):
            call(
                lambda: api.create(
                    "schedules",
                    {
                        "name": name,
                        "kind": kind,
                        "target_type": target_type,
                        "target_id": target_id,
                        "action": action,
                        "scene_id": scene_id,
                        "run_time": run_time.isoformat(),
                        "weekdays": days,
                        "enabled": True,
                    },
                ),
                "Schedule saved",
            )
