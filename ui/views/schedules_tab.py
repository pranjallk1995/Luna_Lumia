"""Schedules tab: recurring schedules and alarms at a time, sunrise, or sunset."""

from datetime import datetime, time, timedelta

import streamlit as st

from domain.dashboard import Item
from views.shared import ActionRunner, LumiaTab
from views.schemes_tab import FormFeedback

WHEN_OPTIONS = {"time": "At a time", "sunrise": "Sunrise", "sunset": "Sunset"}
WHEN_ICONS = {"time": ":material/schedule:", "sunrise": ":material/wb_twilight:", "sunset": ":material/routine:"}


class ScheduleTime:
    """Human-readable schedule times, including sunrise/sunset offsets."""

    @staticmethod
    def offset(minutes: int) -> str:
        if minutes == 0:
            return ""
        return f" {'+' if minutes > 0 else '−'} {abs(minutes)} min"

    @staticmethod
    def shifted(hhmm: str | None, minutes: int) -> str | None:
        """``hhmm`` moved by ``minutes`` (clamped to the same day), for the form preview."""
        if not hhmm:
            return None
        moment = datetime.combine(datetime.today(), time.fromisoformat(hhmm)) + timedelta(minutes=minutes)
        if moment.date() != datetime.today().date():
            return "00:00" if moment.date() < datetime.today().date() else "23:59"
        return moment.strftime("%H:%M")

    @classmethod
    def describe(cls, schedule: Item, has_location: bool) -> str:
        mode = schedule.get("time_mode", "time")
        if mode == "time":
            return schedule["run_time"][:5]
        label = f'{WHEN_OPTIONS[mode]}{cls.offset(schedule.get("offset_minutes", 0))}'
        if not has_location:
            return f"{label} (set a location)"
        today = schedule.get("today_time")
        return f"{label} · {today} today" if today else f"{label} · no {mode} today"


class LocationPanel(LumiaTab):
    """Where sunrise and sunset are calculated for; shows today's times."""

    def render(self) -> None:
        location = self.dashboard.location
        if location:
            sunrise, sunset = location.get("sunrise") or "—", location.get("sunset") or "—"
            st.markdown(
                f'<div class="sun-summary"><span class="material-symbols-rounded">location_on</span>'
                f'<strong>{location["name"]}</strong>'
                f'<span><span class="material-symbols-rounded">wb_twilight</span>Sunrise {sunrise}</span>'
                f'<span><span class="material-symbols-rounded">routine</span>Sunset {sunset}</span></div>',
                unsafe_allow_html=True,
            )
        title = "Change location" if location else "Set your location for sunrise & sunset"
        with st.expander(title, icon=":material/location_on:", expanded=not location):
            st.caption(
                "Sunrise and sunset are calculated on this device from latitude and longitude. "
                "Tip: right-click a place in Google Maps to copy its coordinates."
            )
            with st.form("location_form", border=False):
                name_column, latitude_column, longitude_column = st.columns([2, 1, 1])
                name = name_column.text_input(
                    "Place :red[*]", value=(location or {}).get("name", ""), placeholder="Home", max_chars=80
                )
                latitude = latitude_column.number_input(
                    "Latitude", min_value=-90.0, max_value=90.0, step=0.0001, format="%.4f",
                    value=float((location or {}).get("latitude", 0.0)),
                )
                longitude = longitude_column.number_input(
                    "Longitude", min_value=-180.0, max_value=180.0, step=0.0001, format="%.4f",
                    value=float((location or {}).get("longitude", 0.0)),
                )
                if st.form_submit_button("Save location", icon=":material/save:", use_container_width=True):
                    if not name.strip():
                        st.error("Give the location a name.")
                    else:
                        ActionRunner.run(lambda: self.api.save_location(name, latitude, longitude))


class ScheduleForm(LumiaTab):
    """Create a schedule or alarm; widgets update live (scheme and sun options appear as chosen)."""

    ERROR = "schedule_error"
    ACTIONS = {"on": "On", "off": "Off", "scene": "Color scheme"}

    def day_name(self, weekday: int) -> str:
        return self.config.WEEKDAY_NAMES[weekday]

    def render(self) -> None:
        st.subheader("New schedule or alarm")
        st.session_state.setdefault("schedule_when", "time")
        st.session_state.setdefault("schedule_time", time(7, 0))
        st.session_state.setdefault("schedule_offset", 0)
        st.session_state.setdefault("schedule_days", list(range(7)))
        name_column, kind_column = st.columns([2, 1])
        name_column.text_input("Name :red[*]", placeholder="Wake up", key="schedule_name", max_chars=100)
        kind_column.selectbox("Type", ["schedule", "alarm"], format_func=str.title, key="schedule_kind")
        # When and its time (or sun offset) share one line, split like Target / Action.
        when_column, time_column = st.container(key="schedule_when_row").columns(2, vertical_alignment="bottom")
        when = when_column.segmented_control(
            "When", list(WHEN_OPTIONS),
            format_func=lambda option: f"{WHEN_ICONS[option]} {WHEN_OPTIONS[option]}",
            key="schedule_when", width="stretch",
        ) or "time"
        self._render_time(when, time_column)
        targets = self.dashboard.target_options()
        target_column, action_column = st.columns(2)
        target_column.selectbox("Target", list(targets), key="schedule_target")
        action = action_column.selectbox(
            "Action", list(self.ACTIONS), format_func=self.ACTIONS.__getitem__, key="schedule_action"
        )
        if action == "scene":
            names = {scheme["id"]: scheme["name"] for scheme in self.dashboard.scenes}
            st.selectbox("Color scheme", list(names), format_func=names.__getitem__, key="schedule_scene")
        st.multiselect("Repeat on", list(range(7)), format_func=self.day_name, key="schedule_days")
        st.button(
            "Save schedule", icon=":material/save:", use_container_width=True,
            key="save_schedule", on_click=self.save, args=(targets,),
        )
        FormFeedback.show(self.ERROR)

    def _render_time(self, when: str, column) -> None:
        # The time input and offset slider are only drawn in their own mode, and
        # Streamlit ignores values seeded into a conditional widget's key. So each
        # value lives in a plain key, passed in as ``value`` and copied back.
        state = st.session_state
        if when == "time":
            state["schedule_time"] = column.time_input(
                "Time", value=state["schedule_time"], key="schedule_time_widget"
            )
            return
        location = self.dashboard.location
        offset = state["schedule_offset"] = column.slider(
            f"Offset from {when}", -120, 120, value=state["schedule_offset"], step=5,
            format="%d min", key=f"schedule_offset_widget_{when}",
        )
        preview = ScheduleTime.shifted((location or {}).get(when), offset)
        if preview:
            direction = "before" if offset < 0 else "after"
            relation = f"{abs(offset)} min {direction} {when}" if offset else f"at {when}"
            st.caption(f"Runs {relation} — {preview} today, adjusting daily with the sun.")
        if not location:
            st.info("Set your location above to schedule at sunrise or sunset.", icon=":material/location_on:")

    def save(self, targets: dict) -> None:
        state = st.session_state
        if not state.get("schedule_name", "").strip():
            state[self.ERROR] = "Give the schedule a name."
            return
        when = state.get("schedule_when") or "time"
        target_type, target_id = targets[state["schedule_target"]]
        action = state["schedule_action"]
        payload = {
            "name": state["schedule_name"],
            "kind": state["schedule_kind"],
            "target_type": target_type,
            "target_id": target_id,
            "action": action,
            "scene_id": state.get("schedule_scene") if action == "scene" else None,
            "time_mode": when,
            "run_time": state["schedule_time"].isoformat() if when == "time" else None,
            "offset_minutes": state["schedule_offset"] if when != "time" else 0,
            "weekdays": state["schedule_days"],
            "enabled": True,
        }
        FormFeedback.run(
            self.ERROR,
            lambda: self.api.create("schedules", payload),
            lambda: state.update(schedule_name=""),
        )


class SchedulesTab(LumiaTab):
    def render(self) -> None:
        LocationPanel(self.api, self.config, self.dashboard).render()
        for schedule in self.dashboard.schedules:
            self._render_schedule(schedule)
        ScheduleForm(self.api, self.config, self.dashboard).render()

    def day_name(self, weekday: int) -> str:
        return self.config.WEEKDAY_NAMES[weekday]

    def _render_schedule(self, schedule: Item) -> None:
        with st.container(border=True):
            details, actions = st.columns([5, 1])
            details.subheader(schedule["name"])
            days = ", ".join(self.day_name(day) for day in schedule["weekdays"])
            when = ScheduleTime.describe(schedule, bool(self.dashboard.location))
            action = schedule["action"].title()
            if schedule["action"] == "scene":
                names = {scheme["id"]: scheme["name"] for scheme in self.dashboard.scenes}
                action = f'Scheme: {names.get(schedule.get("scene_id"), "deleted")}'
            details.caption(f'{schedule["kind"].title()} · {when} · {days} · {action}')
            if actions.button("Remove", key=f"dsch{schedule['id']}"):
                ActionRunner.run(lambda: self.api.delete("schedules", schedule["id"]))
