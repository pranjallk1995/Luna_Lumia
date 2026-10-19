"""Schemes tab: solid and sequence schemes, their builders, and transitions."""

import html
from collections.abc import Callable
from itertools import count
from typing import Any

import httpx
import streamlit as st

from domain.dashboard import Item
from views.shared import COLOR, MODE_ICONS, TEMPERATURE, ActionRunner, LumiaTab


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
            apply_column, stop_column, edit_column, delete_column = st.columns([3, 1, 1, 1])
            if apply_column.button(
                "Apply", icon=":material/play_arrow:", key=f"scene{scheme_id}",
                use_container_width=True,
            ):
                ActionRunner.run(lambda: self.api.apply_scene(scheme_id, *target))
            if playing and stop_column.button(
                "", icon=":material/stop:", key=f"stop_scene_{scheme_id}"
            ):
                ActionRunner.run(lambda: self._stop(scheme_id))
            if not scheme["is_preset"] and edit_column.button(
                "", icon=":material/edit:", key=f"edit_scheme_{scheme_id}"
            ):
                SchemeEditor.open_scheme(self.api, self.config, self.dashboard, scheme)
            if not scheme["is_preset"] and delete_column.button(
                "", icon=":material/delete:", key=f"ds{scheme_id}"
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
            "Mode", [TEMPERATURE, COLOR], format_func=MODE_ICONS.__getitem__,
            key=f"{key}_mode", label_visibility="collapsed",
        )
        # Fixed-height body so switching Temperature/Color does not resize the form.
        body = container.container(key=f"{key}_value_body")
        if (mode or TEMPERATURE) == COLOR:
            st.session_state[f"{key}_color"] = body.color_picker(
                "Color", value=st.session_state[f"{key}_color"],
                key=f"{key}_color_widget", label_visibility="collapsed",
            )
        else:
            st.session_state[f"{key}_temp"] = body.slider(
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


class SchemeBuilder(LumiaTab):
    """Shared create/edit behavior for the Solid and Sequence builders.

    The Schemes tab uses a builder to create; the edit dialog uses another
    instance with ``prefix="edit_"`` and the scheme being edited, so the two
    never share widget keys. Saving an edit closes the dialog via ``DONE_KEY``.
    """

    DONE_KEY = "scheme_edit_done"

    def __init__(self, api, config, dashboard, prefix: str = "", editing: Item | None = None) -> None:
        super().__init__(api, config, dashboard)
        self.prefix = prefix
        self.editing = editing

    def k(self, name: str) -> str:
        return f"{self.prefix}{name}"

    @property
    def save_label(self) -> str:
        return "Save changes" if self.editing else self.CREATE_LABEL

    def submit(self, payload: dict[str, Any], name_key: str) -> None:
        if self.editing:
            FormFeedback.run(
                self.k(self.ERROR),
                lambda: self.api.update("scenes", self.editing["id"], payload),
                lambda: st.session_state.update({self.DONE_KEY: True}),
            )
        else:
            FormFeedback.run(
                self.k(self.ERROR),
                lambda: self.api.create("scenes", payload),
                lambda: st.session_state.update({name_key: ""}),
            )


class SolidBuilder(SchemeBuilder):
    """Create or edit a scheme with one color or one white temperature."""

    KEY, ERROR, CREATE_LABEL = "solid", "solid_error", "Save solid scheme"

    def load(self, scheme: Item) -> None:
        """Fill the form from an existing solid scheme."""
        key = self.k(self.KEY)
        st.session_state[self.k("solid_name")] = scheme["name"]
        st.session_state[self.k("solid_brightness")] = scheme["brightness"]
        st.session_state[f"{key}_mode"] = COLOR if scheme["color"] else TEMPERATURE
        st.session_state[f"{key}_color"] = scheme["color"] or LightValueInput.FALLBACKS["color"]
        st.session_state[f"{key}_temp"] = scheme["color_temp"] or LightValueInput.FALLBACKS["temp"]
        st.session_state.pop(self.k(self.ERROR), None)

    def render(self) -> None:
        LightValueInput.defaults(self.k(self.KEY))
        st.session_state.setdefault(self.k("solid_brightness"), 80)
        st.text_input("Name :red[*]", placeholder="Evening glow", key=self.k("solid_name"), max_chars=100)
        LightValueInput(self.config).render(self.k(self.KEY))
        st.slider(":material/brightness_6: Brightness", 1, 100, key=self.k("solid_brightness"))
        st.button(
            self.save_label, icon=":material/save:", use_container_width=True,
            key=self.k("save_solid"), on_click=self.save,
        )
        FormFeedback.show(self.k(self.ERROR))

    def save(self) -> None:
        name_key = self.k("solid_name")
        if not st.session_state.get(name_key, "").strip():
            st.session_state[self.k(self.ERROR)] = "Give the scheme a name."
            return
        self.submit(
            {
                "name": st.session_state[name_key],
                "kind": "solid",
                "brightness": st.session_state[self.k("solid_brightness")],
                **LightValueInput.payload(self.k(self.KEY)),
            },
            name_key,
        )


class SequenceBuilder(SchemeBuilder):
    """Create or edit a chain of colors and temperatures, each held and faded into.

    Step widget keys are ``seq_<uid>_*`` and ``sequence_step_<uid>`` (the
    stylesheet targets them); edit-dialog steps use uids like ``e7``.
    """

    ERROR, CREATE_LABEL = "sequence_error", "Save sequence"
    INSTANT = 0  # option value for "no transition"; None would read as "nothing selected"
    DEFAULT_TRANSITION = "Smooth"
    _ids = count()

    @property
    def steps_key(self) -> str:
        return self.k("sequence_steps")

    def new_uid(self) -> str:
        tag = "e" if self.prefix else ""
        uid = f"{tag}{next(self._ids)}"
        while f"seq_{uid}_mode" in st.session_state:
            uid = f"{tag}{next(self._ids)}"
        return uid

    def new_step(self, after: str | None = None) -> str:
        """Add a step, copying the previous step's settings as a starting point."""
        uid = self.new_uid()
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

    def load(self, scheme: Item) -> None:
        """Fill the form from an existing sequence scheme."""
        options = self.transition_options()
        uids = []
        for step in scheme["steps"]:
            uid = self.new_uid()
            key = f"seq_{uid}"
            st.session_state[f"{key}_mode"] = COLOR if step.get("color") else TEMPERATURE
            st.session_state[f"{key}_color"] = step.get("color") or LightValueInput.FALLBACKS["color"]
            st.session_state[f"{key}_temp"] = step.get("color_temp") or LightValueInput.FALLBACKS["temp"]
            st.session_state[f"{key}_brightness"] = step["brightness"]
            st.session_state[f"{key}_hold"] = step.get("hold_ms", 0) / 1000
            # Built-in "Instant" (or a deleted transition) is the form's Instant option.
            transition_id = step.get("transition_id")
            st.session_state[f"{key}_transition"] = transition_id if transition_id in options else self.INSTANT
            uids.append(uid)
        st.session_state[self.steps_key] = uids
        st.session_state[self.k("sequence_name")] = scheme["name"]
        st.session_state[self.k("sequence_loops")] = scheme["loops"]
        st.session_state.pop(self.k(self.ERROR), None)

    def add_step(self) -> None:
        steps = st.session_state[self.steps_key]
        steps.append(self.new_step(steps[-1] if steps else None))

    def remove_step(self, uid: str) -> None:
        st.session_state[self.steps_key].remove(uid)

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
        if self.steps_key not in st.session_state:
            st.session_state[self.steps_key] = [self.new_step(), self.new_step()]
        st.session_state.setdefault(self.k("sequence_loops"), True)
        st.text_input("Name :red[*]", placeholder="Aurora", key=self.k("sequence_name"), max_chars=100)
        transitions = self.transition_options()
        steps = st.session_state[self.steps_key]
        for position, uid in enumerate(steps, start=1):
            self._render_step(position, uid, transitions, removable=len(steps) > 2)
        add_column, loop_column = st.columns([1, 1], vertical_alignment="center")
        add_column.button(
            "Add step", icon=":material/add:", key=self.k("sequence_add_step"),
            on_click=self.add_step, disabled=len(steps) >= 24,
        )
        loop_column.toggle("Loop", key=self.k("sequence_loops"))
        st.button(
            self.save_label, icon=":material/save:", use_container_width=True,
            key=self.k("save_sequence"), on_click=self.save,
        )
        FormFeedback.show(self.k(self.ERROR))

    def _render_step(
        self, position: int, uid: str, transitions: dict[int, str], removable: bool
    ) -> None:
        key = f"seq_{uid}"
        if st.session_state.get(f"{key}_transition") not in transitions:
            st.session_state[f"{key}_transition"] = self.default_transition()
        with st.container(border=True, key=f"sequence_step_{uid}"):
            title_column, remove_column = st.columns([8, 1], vertical_alignment="center")
            title_column.markdown(f'<div class="scheme-step-title">Step {position}</div>', unsafe_allow_html=True)
            # Always shown; disabled at the two-step minimum a sequence needs.
            remove_column.button(
                "", icon=":material/delete:", key=f"{key}_remove",
                disabled=not removable, on_click=self.remove_step, args=(uid,),
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

    def save(self) -> None:
        name_key = self.k("sequence_name")
        if not st.session_state.get(name_key, "").strip():
            st.session_state[self.k(self.ERROR)] = "Give the sequence a name."
            return
        steps = [
            {
                **LightValueInput.payload(f"seq_{uid}"),
                "brightness": st.session_state[f"seq_{uid}_brightness"],
                "hold_ms": round(st.session_state[f"seq_{uid}_hold"] * 1000),
                "transition_id": st.session_state.get(f"seq_{uid}_transition") or None,
            }
            for uid in st.session_state[self.steps_key]
        ]
        self.submit(
            {
                "name": st.session_state[name_key],
                "kind": "sequence",
                "loops": st.session_state.get(self.k("sequence_loops"), True),
                "steps": steps,
            },
            name_key,
        )


class SchemeEditor:
    """Edit dialogs for user schemes and transitions (built-ins are read-only)."""

    @staticmethod
    def open_scheme(api, config, dashboard, scheme: Item) -> None:
        builder_class = SequenceBuilder if scheme["kind"] == "sequence" else SolidBuilder
        builder_class(api, config, dashboard, prefix="edit_", editing=scheme).load(scheme)
        st.session_state.pop(SchemeBuilder.DONE_KEY, None)

        @st.dialog(f'Edit {scheme["name"]}', width="large")
        def dialog() -> None:
            if st.session_state.pop(SchemeBuilder.DONE_KEY, False):
                st.rerun()
            builder_class(api, config, dashboard, prefix="edit_", editing=scheme).render()

        dialog()

    @staticmethod
    def open_transition(api, transition: Item) -> None:
        @st.dialog(f'Edit {transition["name"]}')
        def dialog() -> None:
            with st.form(f"edit_transition_{transition['id']}", border=False):
                name = st.text_input("Name :red[*]", value=transition["name"], max_chars=60)
                seconds = st.number_input(
                    "Fade (seconds)", min_value=0.0, max_value=600.0,
                    value=transition["duration_ms"] / 1000, step=0.1,
                )
                curves = TransitionManager.CURVES
                curve = st.selectbox("Curve", curves, index=curves.index(transition["curve"]))
                if st.form_submit_button("Save changes", icon=":material/save:", use_container_width=True):
                    if not name.strip():
                        st.error("Give the transition a name.")
                    else:
                        ActionRunner.run(
                            lambda: api.update(
                                "transitions", transition["id"],
                                {"name": name, "duration_ms": round(seconds * 1000), "curve": curve},
                            )
                        )

        dialog()


class TransitionManager(LumiaTab):
    """Saved fades: built-ins are fixed, custom ones can be edited or deleted."""

    CURVES = ("ease-in-out", "linear", "ease-in", "ease-out")

    def render(self) -> None:
        for item in self.dashboard.transitions:
            name_column, detail_column, edit_column, delete_column = st.columns(
                [3, 3, 0.5, 0.5], vertical_alignment="center"
            )
            badge = '<span class="scheme-badge">Built-in</span>' if item["is_preset"] else ""
            name_column.markdown(
                f'<div class="scheme-title">{html.escape(item["name"])}{badge}</div>', unsafe_allow_html=True
            )
            detail_column.markdown(
                f'<div class="scheme-details">{SchemeFormat.seconds(item["duration_ms"])} · {item["curve"]}</div>',
                unsafe_allow_html=True,
            )
            if not item["is_preset"] and edit_column.button(
                "", icon=":material/edit:", key=f"edit_transition_{item['id']}"
            ):
                SchemeEditor.open_transition(self.api, item)
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
