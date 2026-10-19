"""Rooms tab: room and group cards, membership editing, and creation forms."""

import html

import httpx
import streamlit as st

from domain.dashboard import Item
from views.shared import ActionRunner, InlineNameEditor, LumiaTab, NameRules


class RoomSchemePicker:
    """A popover that applies any scheme to one room or group, or stops its sequence."""

    ERROR_KEY = "room_scheme_error_{}"

    def __init__(self, api, dashboard, collection: Item, members: list[Item]) -> None:
        self.api = api
        self.dashboard = dashboard
        self.collection = collection
        self.member_ids = [light["id"] for light in members]

    # Button callbacks run before the next script pass; errors are shown on that pass.
    NOTICE_KEY = "room_scheme_notice"

    @classmethod
    def apply(cls, api, collection_id: int, collection_name: str, scheme_id: int) -> None:
        def run():
            result = api.apply_scene(scheme_id, "group", collection_id) or {}
            count = len(result.get("light_ids", []))
            st.session_state[cls.NOTICE_KEY] = (
                f'{result.get("scene", "Scheme")} applied to {collection_name} '
                f'({count} light{"" if count == 1 else "s"})'
            )

        cls._call(collection_id, run)

    @classmethod
    def show_notice(cls) -> None:
        """Confirm the last room/group apply, naming its target and light count."""
        notice = st.session_state.pop(cls.NOTICE_KEY, None)
        if notice:
            st.toast(notice, icon=":material/palette:")

    @classmethod
    def stop(cls, api, collection_id: int) -> None:
        cls._call(collection_id, lambda: api.stop_scenes("group", collection_id))

    @classmethod
    def _call(cls, collection_id: int, action) -> None:
        try:
            action()
            st.session_state.pop(cls.ERROR_KEY.format(collection_id), None)
        except httpx.HTTPError as error:
            st.session_state[cls.ERROR_KEY.format(collection_id)] = ActionRunner.error_message(error)

    def playing_scheme(self) -> Item | None:
        playing = {self.dashboard.playing.get(light_id) for light_id in self.member_ids} - {None}
        return next((scheme for scheme in self.dashboard.scenes if scheme["id"] in playing), None)

    def render(self) -> None:
        collection_id = self.collection["id"]
        playing = self.playing_scheme()
        label = playing["name"] if playing else ""
        with st.container(key=f"room_scheme_{collection_id}"):
            with st.popover(
                label,
                icon=":material/timeline:" if playing else ":material/palette:",
                disabled=not self.member_ids,
            ):
                st.caption(f'Apply a scheme to {html.escape(self.collection["name"])}')
                if playing:
                    st.button(
                        f'Stop {playing["name"]}', icon=":material/stop:", key=f"room_scheme_stop_{collection_id}",
                        use_container_width=True, on_click=self.stop, args=(self.api, collection_id),
                    )
                for kind, heading, icon in (("solid", "Solid", ":material/lens:"), ("sequence", "Sequence", ":material/timeline:")):
                    schemes = [scheme for scheme in self.dashboard.scenes if scheme["kind"] == kind]
                    if not schemes:
                        continue
                    st.markdown(f'<div class="room-scheme-heading">{heading}</div>', unsafe_allow_html=True)
                    columns = st.columns(2, gap="small")
                    for index, scheme in enumerate(schemes):
                        columns[index % 2].button(
                            scheme["name"], icon=icon, key=f"room_scheme_{collection_id}_{scheme['id']}",
                            use_container_width=True, on_click=self.apply,
                            args=(self.api, collection_id, self.collection["name"], scheme["id"]),
                        )
        if st.session_state.get(self.ERROR_KEY.format(collection_id)):
            st.error(st.session_state[self.ERROR_KEY.format(collection_id)])


class CollectionCard(LumiaTab):
    """A room or group card: image, rename, power, and member-light pills."""

    ORB_ON = ("#ffbe55", "rgba(255,190,85,.72)")
    ORB_ONLINE = ("#22c55e", "rgba(34,197,94,.72)")
    ORB_IDLE = ("#626a79", "transparent")

    def __init__(self, api, config, dashboard, collection: Item) -> None:
        super().__init__(api, config, dashboard)
        self.collection = collection
        self.collection_id = collection["id"]
        self.kind = collection["kind"]
        self.label = self.kind.title()
        self.members = dashboard.member_lights(collection)
        self.is_on = bool(self.members) and all(light.get("is_on") for light in self.members)

    @staticmethod
    def pills_generation_key(collection_id: int) -> str:
        return f"room_light_pills_generation_{collection_id}"

    # Widget callbacks run before the next script pass, so they are static and
    # receive everything they need as arguments.
    @staticmethod
    def sync_power(api, collection_id: int, widget_key: str) -> None:
        """Apply a room toggle change immediately without a notification toast."""
        try:
            api.control("group", collection_id, on=st.session_state[widget_key])
            st.session_state.pop(f"room_control_error_{collection_id}", None)
        except httpx.HTTPError as error:
            st.session_state[f"room_control_error_{collection_id}"] = str(error)

    @classmethod
    def remove_deselected(
        cls, api, kind: str, collection_id: int, widget_key: str, current_ids: tuple[int, ...]
    ) -> None:
        """Remove memberships deselected from the collection's light pills."""
        selected = set(st.session_state.get(widget_key) or [])
        error_key = f"{kind}_membership_error_{collection_id}"
        try:
            for light_id in current_ids:
                if light_id not in selected:
                    api.remove_collection_light(kind, collection_id, light_id)
            st.session_state.pop(error_key, None)
        except httpx.HTTPError as error:
            st.session_state[error_key] = str(error)
        finally:
            generation_key = cls.pills_generation_key(collection_id)
            st.session_state[generation_key] = st.session_state.get(generation_key, 0) + 1

    def render(self) -> None:
        with st.container(border=True, key=f"room_card_{self.collection_id}"):
            layout = st.container(key=f"room_layout_{self.collection_id}")
            image_column, details_column = layout.columns(
                [3.6, 8.4], vertical_alignment="top", gap="medium"
            )
            with image_column, st.container(key=f"room_image_{self.collection_id}"):
                self._render_image()
                InlineNameEditor(
                    "room_", self.collection_id, self.label,
                    lambda name: self.api.update(f"{self.kind}s", self.collection_id, {"name": name}),
                ).render(self.collection["name"], self.is_on)
            with details_column:
                self._render_header()
                self._render_light_row()

    def _render_image(self) -> None:
        # A cover-scaled background (not st.image) always fills the card's
        # image area exactly, whatever the card's size.
        image_url = html.escape(self.collection.get("effective_image_url") or "", quote=True)
        if image_url:
            st.markdown(
                f'<div class="room-card-image" style="background-image:url(\'{image_url}\')"></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="room-card-image"><span class="material-symbols-rounded">meeting_room</span></div>',
                unsafe_allow_html=True,
            )
        if self.is_on:
            st.markdown('<span class="room-image-power-on" aria-label="Room on"></span>', unsafe_allow_html=True)

    def _render_header(self) -> None:
        power_key = f"room_power_{self.collection_id}"
        st.session_state[power_key] = self.is_on
        with st.container(
            key=f"room_header_{self.collection_id}",
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
            gap="small",
        ):
            st.toggle(
                "On",
                key=power_key,
                disabled=not self.members,
                on_change=self.sync_power,
                args=(self.api, self.collection_id, power_key),
            )
            with st.container(
                key=f"room_actions_{self.collection_id}",
                horizontal=True,
                vertical_alignment="center",
                gap="small",
            ):
                RoomSchemePicker(self.api, self.dashboard, self.collection, self.members).render()
                if st.button("", icon=":material/delete:", key=f"dg{self.collection_id}"):
                    ActionRunner.run(lambda: self.api.delete(f"{self.kind}s", self.collection_id))
        if st.session_state.get(f"room_control_error_{self.collection_id}"):
            st.error("Could not update this room.")

    def _render_light_row(self) -> None:
        with st.container(
            key=f"room_light_row_{self.collection_id}",
            horizontal=True,
            vertical_alignment="center",
            gap="small",
        ):
            if self.members:
                self._render_member_pills()
            else:
                st.caption("No lights")
            if st.session_state.get(f"{self.kind}_membership_error_{self.collection_id}"):
                st.error(f"Could not remove this light from the {self.kind}.")
            self._render_add_popover()

    def _pill_status_style(self, index: int, light: Item) -> str:
        """CSS variables that draw each pill's power and online status orbs."""
        online = light.get("reachable") is True
        power_color, power_glow = self.ORB_ON if light.get("is_on") else self.ORB_IDLE
        online_color, online_glow = self.ORB_ONLINE if online else self.ORB_IDLE
        return (
            f'div[class*="st-key-room_light_row_{self.collection_id}"] '
            f'div[data-testid="stButtonGroup"] button:nth-of-type({index})'
            "{"
            f'--room-power-label:"{"On" if light.get("is_on") else "Off"}";'
            f'--room-online-label:"{"Online" if online else "Offline"}";'
            f"--room-power-orb:{power_color};"
            f"--room-power-glow:{power_glow};"
            f"--room-online-orb:{online_color};"
            f"--room-online-glow:{online_glow};"
            "}"
        )

    def _render_member_pills(self) -> None:
        current_ids = tuple(light["id"] for light in self.members)
        generation = st.session_state.get(self.pills_generation_key(self.collection_id), 0)
        pills_key = f"room_light_pills_{self.collection_id}_{generation}"
        status_styles = "".join(
            self._pill_status_style(index, light)
            for index, light in enumerate(self.members, start=1)
        )
        st.markdown('<span class="room-light-removable-pills"></span>', unsafe_allow_html=True)
        st.html(f"<style>{status_styles}</style>")
        st.pills(
            f"{self.label} lights",
            options=list(current_ids),
            default=list(current_ids),
            format_func=self.light_selector_label,
            selection_mode="multi",
            key=pills_key,
            on_change=self.remove_deselected,
            args=(self.api, self.kind, self.collection_id, pills_key, current_ids),
            label_visibility="collapsed",
            width="content",
        )

    def _render_add_popover(self) -> None:
        addable = self.dashboard.addable_light_ids(self.collection)
        with st.popover(":material/add:", width="content"):
            if not addable:
                st.caption(
                    "All lights are already in this group."
                    if self.kind == "group"
                    else "No unassigned lights available."
                )
                return
            with st.form(f"add_room_lights_{self.collection_id}"):
                added_ids = st.multiselect(
                    "Lights", options=addable, format_func=self.light_selector_label
                )
                if st.form_submit_button("Add", use_container_width=True):
                    if not added_ids:
                        st.error("Select at least one light.")
                    else:
                        ActionRunner.run(
                            lambda: self.api.add_collection_lights(
                                self.kind, self.collection_id, added_ids
                            )
                        )


class CollectionCreateForm(LumiaTab):
    """Create a room (unassigned lights only) or a group (any lights)."""

    PLACEHOLDERS = {"room": "Bedroom", "group": "Downstairs"}

    def __init__(self, api, config, dashboard, kind: str) -> None:
        super().__init__(api, config, dashboard)
        self.kind = kind
        self.label = kind.title()

    def render(self) -> None:
        is_room = self.kind == "room"
        options = (
            self.dashboard.unassigned_light_ids()
            if is_room
            else [light["id"] for light in self.dashboard.lights]
        )
        with st.form(f"add_{self.kind}", clear_on_submit=True):
            name = st.text_input(
                f"{self.label} name :red[*]",
                placeholder=self.PLACEHOLDERS[self.kind],
                max_chars=NameRules.MAX_LENGTH,
            )
            light_ids = st.multiselect(
                "Lights :red[*]", options=options, format_func=self.light_selector_label
            )
            if not is_room:
                st.caption("Lights can belong to multiple groups.")
            elif not options:
                st.caption("All lights are already assigned to rooms.")
            if st.form_submit_button(f"Create {self.kind}", use_container_width=True):
                self._submit(name, light_ids)

    def _submit(self, name: str, light_ids: list[int]) -> None:
        if not name.strip():
            st.error(f"Enter a {self.kind} name.")
        elif not NameRules.is_valid(name):
            NameRules.show_invalid(self.label)
        elif not light_ids:
            st.error("Select at least one light.")
        else:
            ActionRunner.run(
                lambda: self.api.create(f"{self.kind}s", {"name": name, "light_ids": light_ids})
            )


class RoomsTab(LumiaTab):
    """List every room then group, followed by the creation forms."""

    def render(self) -> None:
        RoomSchemePicker.show_notice()
        with st.container():
            for collection in self.dashboard.collections:
                CollectionCard(self.api, self.config, self.dashboard, collection).render()
            with st.container(key="room_creation_tabs"):
                room_tab, group_tab = st.tabs(
                    [":material/meeting_room: Room", ":material/group: Group"]
                )
            for tab, kind in ((room_tab, "room"), (group_tab, "group")):
                with tab:
                    CollectionCreateForm(self.api, self.config, self.dashboard, kind).render()
