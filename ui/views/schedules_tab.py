"""Schedules tab: recurring schedules and alarms at a time, sunrise, or sunset."""

import html
from datetime import datetime, time, timedelta

import streamlit as st

from domain.dashboard import Item
from views.shared import ActionRunner, LumiaTab
from views.schemes_tab import FormFeedback, TransitionManager

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

    @staticmethod
    def clock(schedule: Item) -> str:
        """The card's big time: the fixed time, or today's sunrise/sunset time."""
        if schedule.get("time_mode", "time") == "time":
            return schedule["run_time"][:5]
        return schedule.get("today_time") or "--:--"

    @classmethod
    def sun_label(cls, schedule: Item, has_location: bool) -> str | None:
        """How a sunrise/sunset schedule is anchored; None for a fixed time."""
        mode = schedule.get("time_mode", "time")
        if mode == "time":
            return None
        label = f'{WHEN_OPTIONS[mode]}{cls.offset(schedule.get("offset_minutes", 0))}'
        if not has_location:
            return f"{label} · set a location"
        return label if schedule.get("today_time") else f"{label} · no {mode} today"

    @staticmethod
    def days(weekdays: list[int], names: tuple[str, ...]) -> str:
        if len(weekdays) == 7:
            return "Every day"
        if weekdays == [0, 1, 2, 3, 4]:
            return "Weekdays"
        if weekdays == [5, 6]:
            return "Weekends"
        return ", ".join(names[day] for day in weekdays)


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
    """Create or edit a schedule or alarm; widgets update live (scheme and sun options appear as chosen).

    The tab creates with the default keys; the edit dialog uses another instance
    with ``prefix="edit_"`` and the schedule being edited, so the two never share
    widget keys. Saving an edit closes the dialog via ``DONE_KEY``.
    """

    DONE_KEY = "schedule_edit_done"
    ACTIONS = {"on": "On", "off": "Off", "scene": "Color scheme"}

    def __init__(self, api, config, dashboard, prefix: str = "", editing: Item | None = None) -> None:
        super().__init__(api, config, dashboard)
        self.prefix = prefix
        self.editing = editing

    def k(self, name: str) -> str:
        return f"{self.prefix}schedule_{name}"

    def day_name(self, weekday: int) -> str:
        return self.config.WEEKDAY_NAMES[weekday]

    def load(self, schedule: Item) -> None:
        """Seed the edit widgets from ``schedule``."""
        targets = {value: label for label, value in self.dashboard.target_options().items()}
        target = targets.get((schedule["target_type"], schedule.get("target_id")), "All lights")
        run_time = schedule.get("run_time")
        st.session_state.update({
            self.k("name"): schedule["name"],
            self.k("kind"): schedule["kind"],
            self.k("when"): schedule.get("time_mode", "time"),
            self.k("time"): time.fromisoformat(run_time) if run_time else time(7, 0),
            self.k("offset"): schedule.get("offset_minutes", 0),
            self.k("target"): target,
            self.k("action"): schedule["action"],
            self.k("days"): list(schedule["weekdays"]),
        })
        if schedule.get("scene_id") in {scheme["id"] for scheme in self.dashboard.scenes}:
            st.session_state[self.k("scene")] = schedule["scene_id"]
        st.session_state.pop(self.k("error"), None)

    def render(self) -> None:
        if not self.editing:
            st.subheader("New schedule or alarm")
        state = st.session_state
        state.setdefault(self.k("when"), "time")
        state.setdefault(self.k("time"), time(7, 0))
        state.setdefault(self.k("offset"), 0)
        state.setdefault(self.k("days"), list(range(7)))
        name_column, kind_column = st.columns([2, 1])
        name_column.text_input("Name :red[*]", placeholder="Wake up", key=self.k("name"), max_chars=100)
        kind_column.selectbox("Type", ["schedule", "alarm"], format_func=str.title, key=self.k("kind"))
        # When and its time (or sun offset) share one line, split like Target / Action.
        when_column, time_column = st.container(key=self.k("when_row")).columns(2, vertical_alignment="bottom")
        when = when_column.segmented_control(
            "When", list(WHEN_OPTIONS),
            format_func=lambda option: f"{WHEN_ICONS[option]} {WHEN_OPTIONS[option]}",
            key=self.k("when"), width="stretch",
        ) or "time"
        self._render_time(when, time_column)
        targets = self.dashboard.target_options()
        target_column, action_column = st.columns(2)
        target_column.selectbox("Target", list(targets), key=self.k("target"))
        action = action_column.selectbox(
            "Action", list(self.ACTIONS), format_func=self.ACTIONS.__getitem__, key=self.k("action")
        )
        if action == "scene":
            names = {scheme["id"]: scheme["name"] for scheme in self.dashboard.scenes}
            st.selectbox("Color scheme", list(names), format_func=names.__getitem__, key=self.k("scene"))
        st.multiselect("Repeat on", list(range(7)), format_func=self.day_name, key=self.k("days"))
        st.button(
            "Save changes" if self.editing else "Save schedule", icon=":material/save:",
            use_container_width=True, key=self.k("save"), on_click=self.save, args=(targets,),
        )
        FormFeedback.show(self.k("error"))

    def _render_time(self, when: str, column) -> None:
        # The time input and offset slider are only drawn in their own mode, and
        # Streamlit ignores values seeded into a conditional widget's key. So each
        # value lives in a plain key, passed in as ``value`` and copied back.
        state = st.session_state
        if when == "time":
            state[self.k("time")] = column.time_input(
                "Time", value=state[self.k("time")], key=self.k("time_widget")
            )
            return
        location = self.dashboard.location
        offset = state[self.k("offset")] = column.slider(
            f"Offset from {when}", -120, 120, value=state[self.k("offset")], step=5,
            format="%d min", key=self.k(f"offset_widget_{when}"),
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
        error_key = self.k("error")
        if not state.get(self.k("name"), "").strip():
            state[error_key] = "Give the schedule a name."
            return
        when = state.get(self.k("when")) or "time"
        target_type, target_id = targets[state[self.k("target")]]
        action = state[self.k("action")]
        payload = {
            "name": state[self.k("name")],
            "kind": state[self.k("kind")],
            "target_type": target_type,
            "target_id": target_id,
            "action": action,
            "scene_id": state.get(self.k("scene")) if action == "scene" else None,
            "time_mode": when,
            "run_time": state[self.k("time")].isoformat() if when == "time" else None,
            "offset_minutes": state[self.k("offset")] if when != "time" else 0,
            "weekdays": state[self.k("days")],
            "enabled": self.editing.get("enabled", True) if self.editing else True,
        }
        if self.editing:
            FormFeedback.run(
                error_key,
                lambda: self.api.update("schedules", self.editing["id"], payload),
                lambda: state.update({self.DONE_KEY: True}),
            )
        else:
            FormFeedback.run(
                error_key,
                lambda: self.api.create("schedules", payload),
                lambda: state.update({self.k("name"): ""}),
            )

    @classmethod
    def open_editor(cls, api, config, dashboard, schedule: Item) -> None:
        """Edit ``schedule`` in a dialog with the same fields as the create form."""
        cls(api, config, dashboard, prefix="edit_", editing=schedule).load(schedule)
        st.session_state.pop(cls.DONE_KEY, None)
        kind = "alarm" if schedule["kind"] == "alarm" else "schedule"

        @st.dialog(f"Edit {kind}", width="large")
        def dialog() -> None:
            if st.session_state.pop(cls.DONE_KEY, False):
                st.rerun()
            cls(api, config, dashboard, prefix="edit_", editing=schedule).render()

        dialog()


class SchedulesTab(LumiaTab):
    """Location, colorful cards for saved schedules and alarms, and the create form."""

    KIND_ICONS = {"schedule": "schedule", "alarm": "alarm"}

    def render(self) -> None:
        LocationPanel(self.api, self.config, self.dashboard).render()
        schedules = self.dashboard.schedules
        if schedules:
            st.html(self.card_styles())
            per_row = self.config.card_columns
            for index in range(0, len(schedules), per_row):
                for column, schedule in zip(st.columns(per_row), schedules[index : index + per_row]):
                    with column:
                        self._render_card(schedule)
        ScheduleForm(self.api, self.config, self.dashboard).render()

    def card_styles(self) -> str:
        """Give each card a color from the same rotation as the transition cards."""
        palette = TransitionManager.PALETTE
        rules = "".join(
            f".st-key-schedule_card_{item['id']}"
            f"{{--pill-accent:{accent};--pill-fill:{fill};--pill-edge:{edge}}}"
            for index, item in enumerate(self.dashboard.schedules)
            for accent, fill, edge in [palette[index % len(palette)]]
        )
        return f"<style>{rules}</style>"

    def action_label(self, schedule: Item) -> str:
        if schedule["action"] != "scene":
            return f'Turn {schedule["action"]}'
        names = {scheme["id"]: scheme["name"] for scheme in self.dashboard.scenes}
        return names.get(schedule.get("scene_id"), "Deleted scheme")

    def target_label(self, schedule: Item) -> str:
        targets = {value: label for label, value in self.dashboard.target_options().items()}
        return targets.get((schedule["target_type"], schedule.get("target_id")), "Deleted target")

    def _render_card(self, schedule: Item) -> None:
        schedule_id = schedule["id"]
        with st.container(key=f"schedule_card_{schedule_id}"):
            kind = schedule["kind"]
            badges = f'<span class="scheme-badge">{kind.title()}</span>'
            if not schedule.get("enabled", True):
                badges += '<span class="scheme-badge">Paused</span>'
            sun = ScheduleTime.sun_label(schedule, bool(self.dashboard.location))
            chips = (
                ScheduleTime.days(schedule["weekdays"], self.config.WEEKDAY_NAMES),
                self.target_label(schedule),
                self.action_label(schedule),
            )
            st.markdown(
                f'<div class="schedule-name"><span class="material-symbols-rounded">{self.KIND_ICONS.get(kind, "schedule")}</span>'
                f'<span class="schedule-title">{html.escape(schedule["name"])}</span>{badges}</div>'
                f'<div class="schedule-clock">{ScheduleTime.clock(schedule)}</div>'
                + (f'<div class="schedule-sun">{html.escape(sun)}</div>' if sun else "")
                + '<div class="schedule-chips">'
                + "".join(f'<span class="schedule-chip">{html.escape(chip)}</span>' for chip in chips)
                + "</div>",
                unsafe_allow_html=True,
            )
            with st.container(key=f"schedule_tools_{schedule_id}", horizontal=True, gap="small"):
                if st.button("", icon=":material/edit:", key=f"edit_schedule_{schedule_id}"):
                    ScheduleForm.open_editor(self.api, self.config, self.dashboard, schedule)
                if st.button("", icon=":material/delete:", key=f"dsch{schedule_id}"):
                    ActionRunner.run(lambda: self.api.delete("schedules", schedule_id))
