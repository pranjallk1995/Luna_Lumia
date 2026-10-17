"""Schemes tab: saved color schemes and the form to create new ones."""

import html

import streamlit as st

from dashboard import Item
from tabs.shared import ActionRunner, LumiaTab


class SchemesTab(LumiaTab):
    def render(self) -> None:
        scenes = self.dashboard.scenes
        if scenes:
            per_row = self.config.card_columns
            columns = st.columns(per_row)
            for index, scene in enumerate(scenes):
                with columns[index % per_row]:
                    self._render_scene(scene)
        self._render_create_form()

    def _render_scene(self, scene: Item) -> None:
        with st.container(border=True):
            st.markdown(
                f'<div class="light-name"><span class="swatch" style="background:{scene["color"]}"></span>{html.escape(scene["name"])}</div>',
                unsafe_allow_html=True,
            )
            st.caption(f'{scene["color"]} · {scene["brightness"]}% brightness')
            apply_column, delete_column = st.columns([3, 1])
            if apply_column.button("Apply to all", key=f"scene{scene['id']}", use_container_width=True):
                ActionRunner.run(lambda: self.api.apply_scene(scene["id"]))
            if delete_column.button("", icon=":material/delete:", key=f"ds{scene['id']}"):
                ActionRunner.run(lambda: self.api.delete("scenes", scene["id"]))

    def _render_create_form(self) -> None:
        with st.form("add_scene", clear_on_submit=True):
            st.subheader("New color scheme")
            name_column, color_column, brightness_column = st.columns(3)
            name = name_column.text_input("Name", placeholder="Sunset")
            color = color_column.color_picker("Color", "#FF8A5B")
            brightness = brightness_column.slider("Brightness", 1, 100, 70)
            if st.form_submit_button("Save scheme", use_container_width=True):
                ActionRunner.run(
                    lambda: self.api.create(
                        "scenes", {"name": name, "color": color, "brightness": brightness}
                    )
                )
