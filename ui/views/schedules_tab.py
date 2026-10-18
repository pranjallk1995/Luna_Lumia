"""Schedules tab: recurring schedules and alarms."""

from datetime import time

import streamlit as st

from domain.dashboard import Item
from views.shared import ActionRunner, LumiaTab


class SchedulesTab(LumiaTab):
    def render(self) -> None:
        for schedule in self.dashboard.schedules:
            self._render_schedule(schedule)
        self._render_create_form()

    def day_name(self, weekday: int) -> str:
        return self.config.WEEKDAY_NAMES[weekday]

    def _render_schedule(self, schedule: Item) -> None:
        with st.container(border=True):
            details, actions = st.columns([5, 1])
            details.subheader(schedule["name"])
            days = ", ".join(self.day_name(day) for day in schedule["weekdays"])
            details.caption(
                f'{schedule["kind"].title()} · {schedule["run_time"][:5]} · {days} · {schedule["action"].title()}'
            )
            if actions.button("Remove", key=f"dsch{schedule['id']}"):
                ActionRunner.run(lambda: self.api.delete("schedules", schedule["id"]))

    def _scene_selector(self) -> int | None:
        scenes = self.dashboard.scenes
        if not scenes:
            return None
        names = {scene["id"]: scene["name"] for scene in scenes}
        return st.selectbox("Color scheme", list(names), format_func=names.__getitem__)

    def _render_create_form(self) -> None:
        with st.form("add_schedule", clear_on_submit=True):
            st.subheader("New schedule or alarm")
            name_column, kind_column, time_column = st.columns(3)
            name = name_column.text_input("Name", placeholder="Wake up")
            kind = kind_column.selectbox("Type", ["schedule", "alarm"], format_func=str.title)
            run_time = time_column.time_input("Time", value=time(7, 0))
            targets = self.dashboard.target_options()
            target_column, action_column = st.columns(2)
            target_label = target_column.selectbox("Target", list(targets))
            action = action_column.selectbox(
                "Action",
                ["on", "off", "scene"],
                format_func=lambda value: "Color scheme" if value == "scene" else value.title(),
            )
            scene_id = self._scene_selector() if action == "scene" else None
            days = st.multiselect("Repeat on", range(7), default=range(7), format_func=self.day_name)
            target_type, target_id = targets[target_label]
            if st.form_submit_button("Save schedule", use_container_width=True):
                ActionRunner.run(
                    lambda: self.api.create(
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
                    )
                )
