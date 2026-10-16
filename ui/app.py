"""Luna Lumia smart-light dashboard."""

import base64
import hashlib
from datetime import time
import html

import httpx
import streamlit as st
from PIL import Image

from api import LumiaAPI
from config import UIConfig
from styles import LunaStyle


class SourceReloadMonitor:
    """Notify an existing session after Compose Watch syncs UI source."""

    @staticmethod
    def revision() -> str:
        digest = hashlib.sha256()
        source_files = sorted(UIConfig.UI_ROOT.rglob("*.py"))
        source_files.append(UIConfig.UI_ROOT / ".streamlit" / "config.toml")
        source_files.append(UIConfig.LOGO_PATH)
        for source_file in source_files:
            if source_file.is_file():
                digest.update(
                    source_file.relative_to(UIConfig.UI_ROOT).as_posix().encode()
                )
                digest.update(source_file.read_bytes())
        return digest.hexdigest()

    @classmethod
    def notify(cls) -> None:
        revision = cls.revision()
        previous = st.session_state.get("ui_source_revision")
        st.session_state.ui_source_revision = revision
        if previous is not None and previous != revision:
            st.toast("Luna Lumia updated", icon=":material/refresh:")


st.set_page_config(
    page_title="Luna Lumia",
    page_icon=Image.open(UIConfig.LOGO_PATH) if UIConfig.LOGO_PATH.is_file() else "💡",
    layout="wide",
    initial_sidebar_state="collapsed",
)
LunaStyle.apply()
SourceReloadMonitor.notify()
api = LumiaAPI(UIConfig.API_URL)


def call(action, success="Saved"):
    try:
        result = action()
        if success:
            st.toast(success, icon=":material/check:")
        st.rerun()
    except httpx.HTTPStatusError as error:
        try:
            message = error.response.json().get("error", str(error))
        except ValueError:
            message = str(error)
        st.error(message)
    except httpx.HTTPError as error:
        st.error(f"Luna Lumia service is unavailable: {error}")


def select_preset_color(widget_key: str, color: str) -> None:
    st.session_state[widget_key] = color


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
        ":material/group: Groups",
        ":material/palette: Color schemes",
        ":material/schedule: Schedules & alarms",
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
    total_column, on_column, online_column, spacer = st.columns(
        [1, .8, 1, 3.2], vertical_alignment="center"
    )
    total_column.markdown(
        f'<div class="light-stat-card"><span class="material-symbols-rounded total">bolt</span><div><strong>{len(lights)}</strong><small>Total lights</small></div></div>',
        unsafe_allow_html=True,
    )
    on_column.markdown(
        f'<div class="light-stat-card"><span class="status-orb on"></span><div><strong>{on_count}</strong><small>On</small></div></div>',
        unsafe_allow_html=True,
    )
    online_column.markdown(
        f'<div class="light-stat-card"><span class="status-orb online"></span><div><strong>{online_count}</strong><small>Online</small></div></div>',
        unsafe_allow_html=True,
    )
    for index in range(0, len(lights), 3):
        columns = st.columns(3)
        for column, light in zip(columns, lights[index : index + 3]):
            with column, st.container(border=True):
                mac = light.get("mac_address") or "MAC not discovered"
                image_url = html.escape(light.get("effective_image_url") or "", quote=True)
                reachability = "Online" if light["reachable"] else "Status unknown" if light["reachable"] is None else "Offline"
                hero_style = f"background-image:url('{image_url}')" if image_url else ""
                st.markdown(
                    f'<div class="light-card-hero" style="{hero_style}"><span class="light-card-status {"online" if light["reachable"] else ""}"><i></i>{reachability}</span></div>',
                    unsafe_allow_html=True,
                )
                editing_key = f"editing_name_{light['id']}"
                draft_key = f"name_draft_{light['id']}"
                if st.session_state.get(editing_key, False):
                    with st.container(key=f"edit_name_form_{light['id']}"):
                        name_column, confirm_column = st.columns(
                            [5, 1], vertical_alignment="center"
                        )
                        edited_name = name_column.text_input(
                            "Light name",
                            key=draft_key,
                            label_visibility="collapsed",
                            max_chars=100,
                        )
                        if confirm_column.button(
                            ":material/check:",
                            key=f"confirm_name_{light['id']}",
                            help="Save light name",
                            use_container_width=True,
                        ):
                            st.session_state[editing_key] = False
                            call(
                                lambda l=light, n=edited_name: api.update(
                                    "lights", l["id"], {"name": n}
                                ),
                                None,
                            )
                else:
                    if st.button(
                        light["name"],
                        key=f"edit_name_{light['id']}",
                    ):
                        st.session_state[editing_key] = True
                        st.session_state[draft_key] = light["name"]
                        st.rerun()
                st.markdown(
                    f'<div class="light-meta-row"><span class="light-meta">{light["ip_address"]} · {html.escape(mac)}</span></div>',
                    unsafe_allow_html=True,
                )
                is_on = st.toggle("On", value=light["is_on"], key=f"on_{light['id']}")
                brightness = st.slider(
                    ":material/brightness_6: Brightness",
                    1,
                    100,
                    int(light["brightness"]),
                    key=f"brightness_{light['id']}",
                )
                st.markdown(
                    '<div class="light-control-label"><span class="material-symbols-rounded">palette</span><span>Color</span></div>',
                    unsafe_allow_html=True,
                )
                color_key = f"color_{light['id']}"
                color_columns = st.columns(
                    [1.35] + [1] * len(UIConfig.PRESET_COLORS), gap="small"
                )
                color = color_columns[0].color_picker(
                    "Color",
                    light["color"],
                    key=color_key,
                    label_visibility="collapsed",
                )
                for preset_index, (preset_column, preset_color) in enumerate(
                    zip(color_columns[1:], UIConfig.PRESET_COLORS)
                ):
                    preset_column.button(
                        "●",
                        key=f"preset_color_{light['id']}_{preset_color[1:]}",
                        help=f"Use {preset_color}",
                        on_click=select_preset_color,
                        args=(color_key, preset_color),
                    )
                a, b = st.columns([3, 1])
                if a.button(
                    "Apply", key=f"apply_{light['id']}", use_container_width=True
                ):
                    call(
                        lambda l=light, o=is_on, b=brightness, c=color: api.control(
                            "light", l["id"], on=o, brightness=b, color=c
                        ),
                        f"{light['name']} updated",
                    )
                if b.button(
                    "",
                    icon=":material/delete:",
                    key=f"delete_light_{light['id']}",
                    help="Remove light",
                ):
                    call(lambda l=light: api.delete("lights", l["id"]), "Light removed")
    with st.expander("Add a light", icon=":material/add_circle:"):
        with st.form("add_light", clear_on_submit=True):
            name = st.text_input("Name", placeholder="Bedroom lamp")
            ip = st.text_input("IP address", placeholder="192.168.1.20")
            if st.form_submit_button("Add light", use_container_width=True):
                call(
                    lambda: api.create(
                        "lights", {"name": name, "ip_address": ip, "protocol": "wiz"}
                    ),
                    "Light added",
                )

with tab_groups:
    for group in groups:
        with st.container(border=True):
            selected = [
                light["name"] for light in lights if light["id"] in group["light_ids"]
            ]
            a, b = st.columns([5, 1])
            a.subheader(group["name"])
            a.caption(", ".join(selected) or "No lights")
            if b.button("Remove", key=f"dg{group['id']}"):
                call(lambda g=group: api.delete("groups", g["id"]), "Group removed")
            c1, c2, c3 = st.columns(3)
            if c1.button("On", key=f"gon{group['id']}", use_container_width=True):
                call(
                    lambda g=group: api.control("group", g["id"], on=True),
                    "Group turned on",
                )
            if c2.button("Off", key=f"goff{group['id']}", use_container_width=True):
                call(
                    lambda g=group: api.control("group", g["id"], on=False),
                    "Group turned off",
                )
            if scenes and c3.button(
                "Apply first scheme", key=f"gsc{group['id']}", use_container_width=True
            ):
                call(
                    lambda g=group: api.apply_scene(scenes[0]["id"], "group", g["id"]),
                    "Scheme applied",
                )
    with st.form("add_group", clear_on_submit=True):
        st.subheader("Create group")
        name = st.text_input("Group name", placeholder="Downstairs")
        chosen = st.multiselect(
            "Lights",
            options=[light["id"] for light in lights],
            format_func=lambda item: next(
                light["name"] for light in lights if light["id"] == item
            ),
        )
        if st.form_submit_button("Create group", use_container_width=True):
            call(
                lambda: api.create("groups", {"name": name, "light_ids": chosen}),
                "Group created",
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
