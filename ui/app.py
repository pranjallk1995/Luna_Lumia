"""Luna Lumia Streamlit application entry point."""

import base64
from time import monotonic

import httpx
import streamlit as st
from PIL import Image

from services.api import LumiaAPI
from config import UIConfig
from domain.dashboard import Dashboard
from styles import LunaStyle
from views.lights_tab import LightsTab
from views.rooms_tab import RoomsTab
from views.schedules_tab import SchedulesTab
from views.schemes_tab import SchemesTab
from views.shared import ActionRunner


class LunaLumiaApp:
    """Compose and render the Luna Lumia smart-light dashboard."""

    TABS = (
        (":material/lightbulb: Lights", LightsTab),
        (":material/meeting_room: Rooms", RoomsTab),
        (":material/palette: Schemes", SchemesTab),
        (":material/schedule: Schedules", SchedulesTab),
    )

    def __init__(self) -> None:
        self.config = UIConfig.from_env()
        self.api = LumiaAPI(self.config)

    @staticmethod
    @st.fragment(run_every=UIConfig.STATUS_REFRESH_SECONDS)
    def refresh_polled_light_statuses() -> None:
        """Refresh the full dashboard after the backend's periodic status poll."""
        now = monotonic()
        previous = st.session_state.get("last_light_status_refresh")
        st.session_state.last_light_status_refresh = now
        if previous is not None and now - previous >= UIConfig.STATUS_REFRESH_SECONDS - 1:
            st.rerun()

    def load_dashboard(self) -> Dashboard:
        try:
            return Dashboard.from_payload(self.api.dashboard())
        except httpx.HTTPError as error:
            st.error(f"Luna Lumia service is unavailable: {error}")
            st.stop()

    @staticmethod
    def logo_markup() -> str:
        if not UIConfig.LOGO_PATH.is_file():
            return '<div class="lv-placeholder">◉</div>'
        logo_data = base64.b64encode(UIConfig.LOGO_PATH.read_bytes()).decode("ascii")
        return f'<img class="lv-mark" src="data:image/png;base64,{logo_data}" alt="Luna Lumia logo" />'

    def render_header(self, dashboard: Dashboard) -> None:
        brand_column, power_column = st.columns([5, 4], vertical_alignment="center", gap="medium")
        with brand_column:
            st.markdown(
                f'<div class="lv-header">{self.logo_markup()}<div><h1 class="lv-title">Luna Lumia</h1><p class="lv-subtitle">Private AI-managed smart lighting</p></div></div>',
                unsafe_allow_html=True,
            )
        with power_column:
            all_on = dashboard.all_on
            if st.button(
                "Turn all off" if all_on else "Turn all on",
                type="primary",
                use_container_width=True,
                icon=":material/power_settings_new:",
                key="header_all_lights_power",
            ):
                ActionRunner.run(lambda: self.api.control("all", on=not all_on))

    def render(self) -> None:
        LunaStyle.apply()
        self.refresh_polled_light_statuses()
        dashboard = self.load_dashboard()
        self.render_header(dashboard)
        containers = st.tabs([label for label, _ in self.TABS])
        for container, (_, tab_class) in zip(containers, self.TABS):
            with container:
                tab_class(self.api, self.config, dashboard).render()

    @classmethod
    def run(cls) -> None:
        st.set_page_config(
            page_title="Luna Lumia",
            page_icon=Image.open(UIConfig.LOGO_PATH) if UIConfig.LOGO_PATH.is_file() else "💡",
            layout="wide",
            initial_sidebar_state="collapsed",
        )
        cls().render()


if __name__ == "__main__":
    LunaLumiaApp.run()
