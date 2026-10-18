"""Shared Streamlit building blocks for the Luna Lumia tabs."""

from collections.abc import Callable
from typing import Any

import httpx
import streamlit as st

from services.api import LumiaAPI
from config import UIConfig
from domain.dashboard import Dashboard


# Options of the Temperature | Color segmented toggle used wherever a light value is chosen;
# the toggle shows only their icons.
TEMPERATURE, COLOR = "Temperature", "Color"
MODE_ICONS = {TEMPERATURE: ":material/device_thermostat:", COLOR: ":material/palette:"}


class ActionRunner:
    """Run a backend mutation, then rerun on success or surface its error."""

    @staticmethod
    def error_message(error: httpx.HTTPError) -> str:
        if isinstance(error, httpx.HTTPStatusError):
            try:
                return error.response.json().get("error", str(error))
            except ValueError:
                return str(error)
        return f"Luna Lumia service is unavailable: {error}"

    @classmethod
    def run(cls, action: Callable[[], Any]) -> None:
        try:
            action()
            st.rerun()
        except httpx.HTTPError as error:
            st.error(cls.error_message(error))


class NameRules:
    """Mirror the backend's light/room/group naming rule for instant feedback."""

    MAX_LENGTH = 30

    @staticmethod
    def is_valid(value: str) -> bool:
        cleaned = value.strip()
        return bool(cleaned) and all(
            character.isalnum() or character == " " for character in cleaned
        )

    @staticmethod
    def show_invalid(entity: str) -> None:
        st.error(f"{entity} name may contain only letters, numbers, and spaces.")


class InlineNameEditor:
    """A name button that turns into an inline rename form when clicked.

    Widget keys are derived from ``key_prefix`` (``""`` for lights, ``"room_"``
    for rooms and groups) because the stylesheet targets them.
    """

    def __init__(
        self,
        key_prefix: str,
        item_id: int,
        entity_label: str,
        on_rename: Callable[[str], Any],
    ) -> None:
        self.item_id = item_id
        self.entity_label = entity_label
        self.on_rename = on_rename
        self.prefix = key_prefix
        self.editing_key = f"editing_{key_prefix}name_{item_id}"
        self.draft_key = f"{key_prefix}name_draft_{item_id}"

    def render(self, current_name: str, is_on: bool) -> None:
        if st.session_state.get(self.editing_key, False):
            self._render_form()
        elif st.button(
            current_name,
            key=f"edit_{self.prefix}name_{'on' if is_on else 'off'}_{self.item_id}",
        ):
            st.session_state[self.editing_key] = True
            st.session_state[self.draft_key] = current_name
            st.rerun()

    def _render_form(self) -> None:
        with st.container(key=f"edit_{self.prefix}name_form_{self.item_id}"):
            with st.form(key=f"{self.prefix}name_form_{self.item_id}", border=False):
                name_column, confirm_column = st.columns([5, 1], vertical_alignment="center")
                edited_name = name_column.text_input(
                    f"{self.entity_label} name",
                    key=self.draft_key,
                    label_visibility="collapsed",
                    max_chars=NameRules.MAX_LENGTH,
                )
                with confirm_column:
                    submitted = st.form_submit_button(":material/check:", use_container_width=True)
        if not submitted:
            return
        if not NameRules.is_valid(edited_name):
            NameRules.show_invalid(self.entity_label)
            return
        st.session_state[self.editing_key] = False
        ActionRunner.run(lambda: self.on_rename(edited_name))


class LumiaTab:
    """Base class giving every tab the API client, settings, and dashboard data."""

    def __init__(self, api: LumiaAPI, config: UIConfig, dashboard: Dashboard) -> None:
        self.api = api
        self.config = config
        self.dashboard = dashboard

    def light_selector_label(self, light_id: int) -> str:
        return self.dashboard.light_name(light_id)

    def render(self) -> None:
        raise NotImplementedError
