"""Schemes tab: solid and sequence schemes, their builders, and transitions."""

import html
from collections.abc import Callable
from itertools import count
from typing import Any

import httpx
import streamlit as st

from domain.dashboard import Item
from views.shared import ActionRunner, LumiaTab

TEMPERATURE, COLOR = "Temperature", "Color"


class FormFeedback:
    """Run a save from a button callback; keep its error for the next pass."""

    @staticmethod
    def run(error_key: str, action: Callable[[], Any], on_success: Callable[[], None]) -> None:
        try:
            action()
        except httpx.HTTPError as error:
            st.session_state[error_key] = ActionRunner.error_message(error)
            return
        st.session_state.pop(error_key, None)
        on_success()

    @staticmethod
    def show(error_key: str) -> None:
        if st.session_state.get(error_key):
            st.error(st.session_state[error_key])


class SchemeFormat:
    """Human-readable scheme details shared by the library cards."""

    @staticmethod
    def seconds(milliseconds: int) -> str:
        seconds = milliseconds / 1000
        if seconds < 60:
            return f"{seconds:g} s"
        return f"{seconds / 60:g} min"

    @staticmethod
    def light(item: Item) -> str:
        value = f'{item["color_temp"]} K' if item.get("color_temp") else item["color"]
        return f'{value} · {item["brightness"]}%'

    @classmethod
    def details(cls, scheme: Item) -> str:
        if scheme["kind"] == "solid":
            return cls.light(scheme)
        repeat = "loops" if scheme["loops"] else "plays once"
        return f'{len(scheme["steps"])} steps · {cls.seconds(scheme.get("cycle_ms", 0))} · {repeat}'

    @staticmethod
    def preview(scheme: Item) -> str:
        colors = scheme.get("preview_colors") or ["#444444"]
        fill = colors[0] if len(colors) == 1 else f"linear-gradient(90deg,{','.join(colors)})"
        return f'<div class="scheme-preview" style="background:{fill}"></div>'


class SchemeLibrary(LumiaTab):
    """Cards for every scheme with apply, stop, and delete actions."""

    TARGET_KEY = "scheme_apply_target"

    def render(self) -> None:
        targets = self.dashboard.target_options()
        label = st.selectbox("Apply to", list(targets), key=self.TARGET_KEY)
        target = targets[label]
        if self.dashboard.playing and st.button(
            "Stop all sequences", icon=":material/stop_circle:", key="stop_all_sequences"
        ):
            ActionRunner.run(lambda: self.api.stop_scenes("all"))
        per_row = self.config.card_columns
        columns = st.columns(per_row)
        for index, scheme in enumerate(self.dashboard.scenes):
            with columns[index % per_row]:
                self._render_card(scheme, target, label)

    def _render_card(self, scheme: Item, target: tuple[str, int | None], label: str) -> None:
        scheme_id = scheme["id"]
        playing = self.dashboard.lights_playing(scheme_id)
        with st.container(border=True, key=f"scheme_card_{scheme_id}"):
            badges = '<span class="scheme-badge">Built-in</span>' if scheme["is_preset"] else ""
            if playing:
                badges += f'<span class="scheme-badge playing">Playing on {playing}</span>'
            kind = "Sequence" if scheme["kind"] == "sequence" else "Solid"
            st.markdown(
                f"{SchemeFormat.preview(scheme)}"
                f'<div class="scheme-title">{html.escape(scheme["name"])}{badges}</div>'
                f'<div class="scheme-details">{kind} · {html.escape(SchemeFormat.details(scheme))}</div>',
                unsafe_allow_html=True,
            )
            apply_column, stop_column, delete_column = st.columns([3, 1, 1])
            if apply_column.button(
                "Apply", icon=":material/play_arrow:", key=f"scene{scheme_id}",
                use_container_width=True, help=f"Apply to {label}",
            ):
                ActionRunner.run(lambda: self.api.apply_scene(scheme_id, *target))
            if playing and stop_column.button(
                "", icon=":material/stop:", key=f"stop_scene_{scheme_id}", help="Stop this sequence"
            ):
                ActionRunner.run(lambda: self._stop(scheme_id))
            if not scheme["is_preset"] and delete_column.button(
                "", icon=":material/delete:", key=f"ds{scheme_id}", help="Delete scheme"
            ):
                ActionRunner.run(lambda: self.api.delete("scenes", scheme_id))

    def _stop(self, scheme_id: int) -> None:
        for light_id, playing in self.dashboard.playing.items():
            if playing == scheme_id:
                self.api.stop_scenes("light", light_id)


class LightValueInput:
    """A Temperature/Color switch with the matching picker, shared by both builders."""

    FALLBACKS = {"color": "#FF8A5B", "temp": 2700}

    def __init__(self, config) -> None:
        self.config = config

    def render(self, key: str, container=st) -> None:
        # Only one picker is drawn at a time and Streamlit forgets a widget's
        # state while it is hidden, so each value lives in a plain session key
        # ("<key>_color" / "<key>_temp") that seeds the picker when it is drawn.
        self.defaults(key)
        mode = container.segmented_control(
            "Mode", [TEMPERATURE, COLOR], key=f"{key}_mode", label_visibility="collapsed",
        )
        if (mode or TEMPERATURE) == COLOR:
            st.session_state[f"{key}_color"] = container.color_picker(
                "Color", value=st.session_state[f"{key}_color"],
                key=f"{key}_color_widget", label_visibility="collapsed",
            )
        else:
            st.session_state[f"{key}_temp"] = container.slider(
                "Temperature", self.config.MIN_COLOR_TEMP, self.config.MAX_COLOR_TEMP,
                value=st.session_state[f"{key}_temp"], step=100, format="%dK",
                key=f"{key}_temp_widget", label_visibility="collapsed",
            )

    @classmethod
    def defaults(cls, key: str, mode: str = TEMPERATURE) -> None:
        st.session_state.setdefault(f"{key}_mode", mode)
        for suffix, value in cls.FALLBACKS.items():
            st.session_state.setdefault(f"{key}_{suffix}", value)

    @staticmethod
    def payload(key: str) -> dict[str, Any]:
        if (st.session_state.get(f"{key}_mode") or TEMPERATURE) == COLOR:
            return {"color": st.session_state[f"{key}_color"]}
        return {"color_temp": st.session_state[f"{key}_temp"]}


class SolidBuilder(LumiaTab):
    """Create a scheme with one color or one white temperature."""

    KEY, ERROR = "solid", "solid_error"

    def render(self) -> None:
        LightValueInput.defaults(self.KEY)
        st.session_state.setdefault("solid_brightness", 80)
        st.text_input("Name", placeholder="Evening glow", key="solid_name", max_chars=100)
        LightValueInput(self.config).render(self.KEY)
        st.slider(":material/brightness_6: Brightness", 1, 100, key="solid_brightness")
        st.button(
            "Save solid scheme", icon=":material/save:", use_container_width=True,
            key="save_solid", on_click=self.save, args=(self.api,),
        )
        FormFeedback.show(self.ERROR)

    @classmethod
    def save(cls, api) -> None:
        payload = {
            "name": st.session_state.get("solid_name", ""),
            "kind": "solid",
            "brightness": st.session_state["solid_brightness"],
            **LightValueInput.payload(cls.KEY),
        }
        FormFeedback.run(
            cls.ERROR,
            lambda: api.create("scenes", payload),
            lambda: st.session_state.update(solid_name=""),
        )


class SequenceBuilder(LumiaTab):
    """Chain colors and temperatures, each held for a time and faded into."""

    STEPS_KEY, ERROR = "sequence_steps", "sequence_error"
    _ids = count()

    @classmethod
    def new_step(cls, after: int | None = None) -> int:
        """Add a step, copying the previous step's settings as a starting point."""
        uid = next(cls._ids)
        while f"seq_{uid}_mode" in st.session_state:
            uid = next(cls._ids)
        key = f"seq_{uid}"
        if after is None:
            LightValueInput.defaults(key)
            st.session_state.setdefault(f"{key}_brightness", 80)
            st.session_state.setdefault(f"{key}_hold", 1.0)
        else:
            source = f"seq_{after}"
            for suffix in ("mode", "color", "temp", "brightness", "hold", "transition"):
                value = st.session_state.get(f"{source}_{suffix}")
                if value is not None:
                    st.session_state[f"{key}_{suffix}"] = value
        return uid

    @classmethod
    def add_step(cls) -> None:
        steps = st.session_state[cls.STEPS_KEY]
        steps.append(cls.new_step(steps[-1] if steps else None))

    @classmethod
    def remove_step(cls, uid: int) -> None:
        st.session_state[cls.STEPS_KEY].remove(uid)

    INSTANT = 0  # option value for "no transition"; None would read as "nothing selected"
    DEFAULT_TRANSITION = "Smooth"

    def transition_options(self) -> dict[int, str]:
        options = {self.INSTANT: "Instant"}
        for item in self.dashboard.transitions:
            if item["duration_ms"] or item["name"] != "Instant":
                options[item["id"]] = (
                    f'{item["name"]} · {SchemeFormat.seconds(item["duration_ms"])} {item["curve"]}'
                )
        return options

    def default_transition(self) -> int:
        return next(
            (item["id"] for item in self.dashboard.transitions if item["name"] == self.DEFAULT_TRANSITION),
            self.INSTANT,
        )

    def render(self) -> None:
        if self.STEPS_KEY not in st.session_state:
            st.session_state[self.STEPS_KEY] = [self.new_step(), self.new_step()]
        st.text_input("Name", placeholder="Aurora", key="sequence_name", max_chars=100)
        transitions = self.transition_options()
        steps = st.session_state[self.STEPS_KEY]
        for position, uid in enumerate(steps, start=1):
            self._render_step(position, uid, transitions, removable=len(steps) > 2)
        add_column, loop_column = st.columns([1, 1], vertical_alignment="center")
        add_column.button(
            "Add step", icon=":material/add:", key="sequence_add_step",
            on_click=self.add_step, disabled=len(steps) >= 24,
        )
        loop_column.toggle("Loop", value=True, key="sequence_loops")
        st.button(
            "Save sequence", icon=":material/save:", use_container_width=True,
            key="save_sequence", on_click=self.save, args=(self.api,),
        )
        FormFeedback.show(self.ERROR)

    def _render_step(
        self, position: int, uid: int, transitions: dict[int, str], removable: bool
    ) -> None:
        key = f"seq_{uid}"
        if st.session_state.get(f"{key}_transition") not in transitions:
            st.session_state[f"{key}_transition"] = self.default_transition()
        with st.container(border=True, key=f"sequence_step_{uid}"):
            title_column, remove_column = st.columns([8, 1], vertical_alignment="center")
            title_column.markdown(f'<div class="scheme-step-title">Step {position}</div>', unsafe_allow_html=True)
            if removable:
                remove_column.button(
                    "", icon=":material/close:", key=f"{key}_remove", help="Remove step",
                    on_click=self.remove_step, args=(uid,),
                )
            value_column, brightness_column = st.columns(2, vertical_alignment="bottom")
            LightValueInput(self.config).render(key, value_column)
            brightness_column.slider(":material/brightness_6: Brightness", 1, 100, key=f"{key}_brightness")
            transition_column, hold_column = st.columns(2)
            options = list(transitions)
            # Kept in a plain key (like the pickers) so the choice survives reruns.
            st.session_state[f"{key}_transition"] = transition_column.selectbox(
                "Fade in" if position > 1 else "Fade in (when looping back)",
                options,
                index=options.index(st.session_state[f"{key}_transition"]),
                format_func=transitions.__getitem__,
                key=f"{key}_transition_widget",
            )
            hold_column.number_input(
                "Hold (seconds)", min_value=0.0, max_value=3600.0, step=0.1, key=f"{key}_hold",
            )

    @classmethod
    def save(cls, api) -> None:
        steps = [
            {
                **LightValueInput.payload(f"seq_{uid}"),
                "brightness": st.session_state[f"seq_{uid}_brightness"],
                "hold_ms": round(st.session_state[f"seq_{uid}_hold"] * 1000),
                "transition_id": st.session_state.get(f"seq_{uid}_transition") or None,
            }
            for uid in st.session_state[cls.STEPS_KEY]
        ]
        payload = {
            "name": st.session_state.get("sequence_name", ""),
            "kind": "sequence",
            "loops": st.session_state.get("sequence_loops", True),
            "steps": steps,
        }
        FormFeedback.run(
            cls.ERROR,
            lambda: api.create("scenes", payload),
            lambda: st.session_state.update(sequence_name=""),
        )


class TransitionManager(LumiaTab):
    """Saved fades: built-ins are fixed, custom ones can be deleted."""

    CURVES = ("ease-in-out", "linear", "ease-in", "ease-out")

    def render(self) -> None:
        for item in self.dashboard.transitions:
            name_column, detail_column, delete_column = st.columns([3, 3, 1], vertical_alignment="center")
            badge = '<span class="scheme-badge">Built-in</span>' if item["is_preset"] else ""
            name_column.markdown(
                f'<div class="scheme-title">{html.escape(item["name"])}{badge}</div>', unsafe_allow_html=True
            )
            detail_column.markdown(
                f'<div class="scheme-details">{SchemeFormat.seconds(item["duration_ms"])} · {item["curve"]}</div>',
                unsafe_allow_html=True,
            )
            if not item["is_preset"] and delete_column.button(
                "", icon=":material/delete:", key=f"delete_transition_{item['id']}"
            ):
                ActionRunner.run(lambda item_id=item["id"]: self.api.delete("transitions", item_id))
        with st.form("add_transition", clear_on_submit=True):
            st.subheader("New transition")
            name_column, duration_column, curve_column = st.columns(3)
            name = name_column.text_input("Name", placeholder="Gentle", max_chars=60)
            seconds = duration_column.number_input(
                "Fade (seconds)", min_value=0.0, max_value=600.0, value=1.0, step=0.1
            )
            curve = curve_column.selectbox("Curve", self.CURVES)
            if st.form_submit_button("Save transition", use_container_width=True):
                ActionRunner.run(
                    lambda: self.api.create(
                        "transitions",
                        {"name": name, "duration_ms": round(seconds * 1000), "curve": curve},
                    )
                )


class SchemesTab(LumiaTab):
    def render(self) -> None:
        with st.container(key="scheme_sections"):
            library, solid, sequence, transitions = st.tabs(
                [
                    ":material/palette: Library",
                    ":material/lens: Solid",
                    ":material/timeline: Sequence",
                    ":material/swap_horiz: Transitions",
                ]
            )
        sections = (
            (library, SchemeLibrary),
            (solid, SolidBuilder),
            (sequence, SequenceBuilder),
            (transitions, TransitionManager),
        )
        for container, section in sections:
            with container:
                section(self.api, self.config, self.dashboard).render()
