"""Lights tab: network discovery, per-light control cards, and manual add."""

import html

import httpx
import streamlit as st

from dashboard import Item
from tabs.shared import ActionRunner, InlineNameEditor, LumiaTab, NameRules


class DiscoveryPanel(LumiaTab):
    """Scan the LAN for WiZ lights and offer to add the ones not yet saved."""

    RESULTS_KEY = "discovered_lights"

    def render(self) -> None:
        with st.container(border=True):
            self._render_scan_header()
            discovered = st.session_state.get(self.RESULTS_KEY)
            if discovered is not None:
                self._render_results(discovered)

    def _render_scan_header(self) -> None:
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
                    st.session_state[self.RESULTS_KEY] = self.api.discover(
                        self.config.discovery_broadcast
                    )
            except httpx.HTTPError as error:
                st.error(f"Network scan failed: {error}")

    def _render_results(self, discovered: list[Item]) -> None:
        with st.expander(
            f"Found lights ({len(discovered)})", expanded=True, icon=":material/lightbulb:"
        ):
            st.markdown('<span class="discovery-results-marker"></span>', unsafe_allow_html=True)
            if not discovered:
                st.info(
                    "No WiZ lights answered the scan. Confirm they are powered on and connected to the 192.168.1.x network."
                )
            configured_ips = self.dashboard.configured_ips
            for bulb in discovered:
                self._render_bulb(bulb, bulb["ip_address"] in configured_ips)

    def _render_bulb(self, bulb: Item, already_added: bool) -> None:
        ip_address = bulb["ip_address"]
        bulb_row, add_column = st.columns([4, 1], vertical_alignment="bottom")
        with bulb_row:
            proposed_name = st.text_input(
                f'{ip_address} · {bulb.get("mac_address") or "MAC unavailable"}',
                value=bulb["suggested_name"],
                disabled=already_added,
                key=f'discovered_name_{ip_address.replace(".", "_")}',
            )
        if already_added:
            add_column.button(
                "Added", disabled=True, use_container_width=True, key=f"discovered_added_{ip_address}"
            )
        elif add_column.button("Add", use_container_width=True, key=f"discovered_add_{ip_address}"):
            ActionRunner.run(
                lambda: self.api.create(
                    "lights",
                    {
                        "name": proposed_name,
                        "ip_address": ip_address,
                        "protocol": "wiz",
                        "mac_address": bulb.get("mac_address"),
                    },
                )
            )


class LightCard(LumiaTab):
    """One light's hero image, inline rename, power, brightness, and color."""

    def __init__(self, api, config, dashboard, light: Item) -> None:
        super().__init__(api, config, dashboard)
        self.light = light
        self.light_id = light["id"]
        self.color_key = f"color_{self.light_id}"

    # Widget callbacks run before the next script pass, so they read widget
    # values from session state rather than from this card instance.
    @staticmethod
    def sync_controls(api, light_id: int) -> None:
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

    @classmethod
    def select_preset_color(cls, api, light_id: int, color: str) -> None:
        st.session_state[f"color_{light_id}"] = color
        cls.sync_controls(api, light_id)

    def render(self) -> None:
        with st.container(border=True):
            self._render_hero()
            InlineNameEditor(
                "", self.light_id, "Light",
                lambda name: self.api.rename_light(self.light_id, name),
            ).render(self.light["name"], self.light["is_on"])
            self._render_meta()
            self._render_controls()
            if st.session_state.get(f"control_error_{self.light_id}"):
                st.error("Could not update this light.")
            self._render_actions()

    def _render_hero(self) -> None:
        light = self.light
        image_url = html.escape(light.get("effective_image_url") or "", quote=True)
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

    def _render_meta(self) -> None:
        mac = self.light.get("mac_address") or "MAC not discovered"
        st.markdown(
            f'<div class="light-meta-row"><span class="light-meta">{self.light["ip_address"]} · {html.escape(mac)}</span></div>',
            unsafe_allow_html=True,
        )

    def _render_controls(self) -> None:
        sync_args = (self.api, self.light_id)
        st.toggle(
            "On",
            value=self.light["is_on"],
            key=f"on_{self.light_id}",
            on_change=self.sync_controls,
            args=sync_args,
        )
        st.slider(
            ":material/brightness_6: Brightness",
            1,
            100,
            int(self.light["brightness"]),
            key=f"brightness_{self.light_id}",
            on_change=self.sync_controls,
            args=sync_args,
        )
        st.markdown(
            '<div class="light-control-label"><span class="material-symbols-rounded">palette</span><span>Color</span></div>',
            unsafe_allow_html=True,
        )
        if self.color_key not in st.session_state:
            st.session_state[self.color_key] = self.light["color"]
        presets = self.config.PRESET_COLORS
        with st.container(key=f"light_color_controls_{self.light_id}"):
            color_columns = st.columns([1.35] + [1] * len(presets), gap="small")
            color_columns[0].color_picker(
                "Color",
                key=self.color_key,
                label_visibility="collapsed",
                on_change=self.sync_controls,
                args=sync_args,
            )
            for preset_column, preset_color in zip(color_columns[1:], presets):
                preset_column.button(
                    "●",
                    key=f"preset_color_{self.light_id}_{preset_color[1:]}",
                    help=f"Use {preset_color}",
                    on_click=self.select_preset_color,
                    args=(*sync_args, preset_color),
                )

    def _render_actions(self) -> None:
        room_names = self.dashboard.room_names_by_light.get(self.light_id, [])
        with st.container(key=f"light_card_actions_{self.light_id}"):
            room_column, delete_column = st.columns([8, 1], vertical_alignment="center")
            if room_names:
                room_column.markdown(
                    f'<span class="light-room-membership"><span class="material-symbols-rounded">meeting_room</span>{html.escape(", ".join(room_names))}</span>',
                    unsafe_allow_html=True,
                )
            if delete_column.button("", icon=":material/delete:", key=f"delete_light_{self.light_id}"):
                ActionRunner.run(lambda: self.api.delete("lights", self.light_id))


class LightsTab(LumiaTab):
    """Compose discovery, light statistics, the light-card grid, and manual add."""

    def render(self) -> None:
        DiscoveryPanel(self.api, self.config, self.dashboard).render()
        self._render_stats()
        self._render_cards()
        self._render_add_form()

    def _render_stats(self) -> None:
        lights = self.dashboard.lights
        on_count = sum(bool(light.get("is_on")) for light in lights)
        online_count = sum(light.get("reachable") is True for light in lights)
        st.markdown(
            f'<div class="light-stats-row"><div class="light-stat-card"><span class="material-symbols-rounded total">bolt</span><div><strong>{len(lights)}</strong><small>Total lights</small></div></div><div class="light-stat-card"><span class="status-orb on"></span><div><strong>{on_count}</strong><small>On</small></div></div><div class="light-stat-card"><span class="status-orb online"></span><div><strong>{online_count}</strong><small>Online</small></div></div></div>',
            unsafe_allow_html=True,
        )

    def _render_cards(self) -> None:
        lights, per_row = self.dashboard.lights, self.config.card_columns
        for index in range(0, len(lights), per_row):
            for column, light in zip(st.columns(per_row), lights[index : index + per_row]):
                with column:
                    LightCard(self.api, self.config, self.dashboard, light).render()

    def _render_add_form(self) -> None:
        with st.expander("Add a light", icon=":material/add_circle:"):
            with st.form("add_light", clear_on_submit=True):
                name = st.text_input("Name", placeholder="Bedroom lamp", max_chars=NameRules.MAX_LENGTH)
                ip_address = st.text_input("IP address", placeholder="192.168.1.20")
                if st.form_submit_button("Add light", use_container_width=True):
                    if not NameRules.is_valid(name):
                        NameRules.show_invalid("Light")
                    else:
                        ActionRunner.run(
                            lambda: self.api.create(
                                "lights",
                                {"name": name, "ip_address": ip_address, "protocol": "wiz"},
                            )
                        )
