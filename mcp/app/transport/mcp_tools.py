"""MCP tools that let LLM clients manage Luna Lumia lights."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from app.core.models import (
    GroupCreate,
    GroupMembersUpdate,
    GroupUpdate,
    LightImageUpdate,
    LightState,
    LocationUpdate,
    MusicAutomationUpdate,
    MusicBeatsUpdate,
    MusicSlot,
    RoomImageUpdate,
    SceneCreate,
    ScheduleCreate,
    TransitionCreate,
    WeatherAutomationUpdate,
    WeatherReport,
    WeatherSlot,
)
from app.services.application import LumiaService
from app.core.config import AppConfig


class LumiaMCPTools:
    """Register Luna Lumia's MCP tool surface on a FastMCP server."""

    def __init__(self, server: FastMCP, service: LumiaService) -> None:
        self.server = server
        self.service = service
        self._register_inventory_tools()
        self._register_image_tools()
        self._register_scheme_tools()
        self._register_control_tools()
        self._register_schedule_tools()
        self._register_weather_tools()
        self._register_music_tools()

    def _register_inventory_tools(self) -> None:
        server, lights, collections = self.server, self.service.lights, self.service.collections

        @server.tool()
        def list_lights():
            """List configured Luna Lumia lights and their last known states (see refresh_light_statuses)."""
            return lights.list()

        @server.tool()
        async def refresh_light_statuses():
            """Ask every light for its current power, brightness, color, and reachability, and save it.

            Lumia does not poll in the background, so call this before relying on
            list_lights if a light may have been changed outside Lumia. A light that
            moved to a new IP address is found again by its MAC address.
            """
            return await self.service.refresh_lights()

        @server.tool()
        def list_rooms():
            """List available rooms, their member lights, and background images."""
            return collections.list_with_images("room")

        @server.tool()
        def list_groups():
            """List available reusable groups, their member lights, and background images."""
            return collections.list_with_images("group")

        @server.tool()
        def get_room(room_id: int):
            """Get one room by id."""
            return collections.get(room_id, "room")

        @server.tool()
        def get_group(group_id: int):
            """Get one reusable group by id."""
            return collections.get(group_id, "group")

        @server.tool()
        def create_room(name: str, light_ids: list[int]):
            """Create a room. A light can belong to only one room."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "room")

        @server.tool()
        def create_group(name: str, light_ids: list[int]):
            """Create a reusable group. Lights may belong to multiple groups."""
            return collections.create(GroupCreate(name=name, light_ids=light_ids), "group")

        @server.tool()
        def rename_room(room_id: int, name: str):
            """Rename a room and refresh its inferred background image."""
            entry = GroupUpdate(name=name)
            return collections.rename(room_id, "room", entry.name)

        @server.tool()
        def rename_group(group_id: int, name: str):
            """Rename a reusable group."""
            entry = GroupUpdate(name=name)
            return collections.rename(group_id, "group", entry.name)

        @server.tool()
        def add_lights_to_room(room_id: int, light_ids: list[int]):
            """Add lights to a room. Lights already assigned to another room are rejected."""
            entry = GroupMembersUpdate(light_ids=light_ids)
            return collections.add_members(room_id, "room", entry.light_ids)

        @server.tool()
        def add_lights_to_group(group_id: int, light_ids: list[int]):
            """Add lights to a group. The same lights may also belong to other groups."""
            entry = GroupMembersUpdate(light_ids=light_ids)
            return collections.add_members(group_id, "group", entry.light_ids)

        @server.tool()
        def remove_light_from_room(room_id: int, light_id: int):
            """Remove one light from a room without deleting the light."""
            collections.remove_member(room_id, "room", light_id)
            return {"removed": True, "room_id": room_id, "light_id": light_id}

        @server.tool()
        def remove_light_from_group(group_id: int, light_id: int):
            """Remove one light from a group without deleting the light."""
            collections.remove_member(group_id, "group", light_id)
            return {"removed": True, "group_id": group_id, "light_id": light_id}

        @server.tool()
        def delete_room(room_id: int):
            """Delete a room without deleting its lights."""
            collections.delete(room_id, "room")
            return {"deleted": True, "room_id": room_id}

        @server.tool()
        def delete_group(group_id: int):
            """Delete a reusable group without deleting its lights."""
            collections.delete(group_id, "group")
            return {"deleted": True, "group_id": group_id}

        @server.tool()
        async def discover_lights_on_network(broadcast_space: str = AppConfig.GLOBAL_BROADCAST):
            """Scan the local network for WiZ-compatible smart lights."""
            return await lights.discover(broadcast_space)

    def _register_image_tools(self) -> None:
        server, images = self.server, self.service.images

        @server.tool()
        def list_room_images():
            """List the room background image URLs used by Lumia light cards."""
            return images.list_room_images()

        @server.tool()
        def update_room_image(room_key: str, image_url: str):
            """Add or update the image URL used for a Lumia room type."""
            entry = RoomImageUpdate(room_key=room_key, image_url=image_url)
            return images.update_room_image(entry.room_key, entry.image_url)

        @server.tool()
        def set_light_background_image(
            light_id: int,
            image_url: str | None = None,
            room_name: str | None = None,
        ):
            """Assign a light image. Without a URL, infer it from room_name or the light name while preserving the available image scheme."""
            entry = LightImageUpdate(image_url=image_url)
            return images.apply_light_image(light_id, entry.image_url, room_name)

        @server.tool()
        def clear_light_background_image(light_id: int):
            """Clear a light-specific image override so the dashboard resolves its room image dynamically."""
            return images.set_light_image(light_id, None)

        @server.tool()
        def set_room_background_image(
            group_id: int,
            image_url: str | None = None,
            room_name: str | None = None,
        ):
            """Assign a room card image. Without a URL, infer it from the room name or member-light names and match the existing Visia image scheme."""
            entry = LightImageUpdate(image_url=image_url)
            return images.apply_collection_image(group_id, entry.image_url, room_name)

    def _register_scheme_tools(self) -> None:
        server, scenes, transitions = self.server, self.service.scenes, self.service.transitions

        @server.tool()
        def list_schemes():
            """List color schemes (solid and sequence), transitions, and what is playing per light.

            Each scheme's "weather_slots" lists the weather it plays for (e.g. "rain/night"),
            and "music_moods" the moods of music it plays for (e.g. "sleep").
            """
            return {
                "schemes": self.service.decorate(scenes.list()),
                "transitions": transitions.list(),
                "playing": scenes.playing(),
            }

        @server.tool()
        def create_solid_scheme(
            name: str, brightness: int, color: str | None = None, color_temp: int | None = None
        ):
            """Save a solid scheme: one #RRGGBB color or one white color_temp (2200-6500 K)."""
            return scenes.add(
                SceneCreate(name=name, brightness=brightness, color=color, color_temp=color_temp)
            )

        @server.tool()
        def create_sequence_scheme(name: str, steps: list[dict[str, Any]], loops: bool = True):
            """Save a sequence scheme of 2-24 steps that play in order (and repeat if loops).

            Each step: {"color": "#RRGGBB"} or {"color_temp": 2200-6500}, "brightness" 1-100,
            "hold_ms" (time to stay on the step), and "transition_id" (the fade into the step;
            see list_schemes for transitions; omit for an instant change).
            """
            return scenes.add(SceneCreate(name=name, kind="sequence", steps=steps, loops=loops))

        @server.tool()
        def update_solid_scheme(
            scheme_id: int, name: str, brightness: int, color: str | None = None, color_temp: int | None = None
        ):
            """Replace one of your solid schemes (built-ins cannot be edited); same fields as create_solid_scheme."""
            return scenes.update(
                scheme_id,
                SceneCreate(name=name, brightness=brightness, color=color, color_temp=color_temp),
            )

        @server.tool()
        def update_sequence_scheme(scheme_id: int, name: str, steps: list[dict[str, Any]], loops: bool = True):
            """Replace one of your sequence schemes (built-ins cannot be edited); same fields as create_sequence_scheme.

            A sequence that is playing restarts with the new steps.
            """
            return scenes.update(scheme_id, SceneCreate(name=name, kind="sequence", steps=steps, loops=loops))

        @server.tool()
        def update_transition(transition_id: int, name: str, duration_ms: int, curve: str = "ease-in-out"):
            """Replace one of your transitions (built-ins cannot be edited); same fields as create_transition."""
            return transitions.update(
                transition_id, TransitionCreate(name=name, duration_ms=duration_ms, curve=curve)
            )

        @server.tool()
        def create_transition(name: str, duration_ms: int, curve: str = "ease-in-out"):
            """Save a reusable fade: duration_ms (0-600000) and curve (linear, ease-in, ease-out, ease-in-out)."""
            return transitions.add(TransitionCreate(name=name, duration_ms=duration_ms, curve=curve))

        @server.tool()
        async def apply_scheme(
            scheme_id: int, target_type: str = "all", target_id: int | None = None
        ):
            """Apply a scheme to all lights, one light, or a room/group.

            Use target_type "all", "light", or "group". Rooms and groups both use
            "group" with their collection id.
            """
            return await scenes.apply(target_type, target_id, scheme_id)

        @server.tool()
        def stop_scheme(target_type: str = "all", target_id: int | None = None):
            """Stop sequence schemes on all lights, one light, or a room/group."""
            return scenes.stop(target_type, target_id)

        @server.tool()
        def delete_scheme(scheme_id: int):
            """Delete a user-created light scheme. Built-in schemes are protected."""
            scenes.delete(scheme_id)
            return {"deleted": True, "scheme_id": scheme_id}

        @server.tool()
        def delete_transition(transition_id: int):
            """Delete a user-created transition. Built-in transitions are protected."""
            transitions.delete(transition_id)
            return {"deleted": True, "transition_id": transition_id}

    def _register_control_tools(self) -> None:
        server, control, scenes = self.server, self.service.control, self.service.scenes

        @server.tool()
        async def set_light(
            light_id: int,
            on: bool | None = None,
            brightness: int | None = None,
            color: str | None = None,
            color_temp: int | None = None,
        ):
            """Control one light by id. Color is a #RRGGBB value; color_temp is white light in Kelvin (2200-6500). Set one of color or color_temp."""
            state = LightState(on=on, brightness=brightness, color=color, color_temp=color_temp)
            return await control.control("light", light_id, state)

        @server.tool()
        async def set_all_lights(on: bool):
            """Turn all configured lights on or off."""
            return await control.control("all", None, LightState(on=on))

        @server.tool()
        async def set_group(
            group_id: int,
            on: bool | None = None,
            brightness: int | None = None,
            color: str | None = None,
            color_temp: int | None = None,
        ):
            """Control every light in a saved group. Set one of color (#RRGGBB) or color_temp (Kelvin, 2200-6500)."""
            state = LightState(on=on, brightness=brightness, color=color, color_temp=color_temp)
            return await control.control("group", group_id, state)

        @server.tool()
        async def activate_scene(scene_id: int, target_type: str = "all", target_id: int | None = None):
            """Apply a saved scheme to "all" lights, one "light", or a "group" (rooms are groups).

            Solid schemes are set at once; sequence schemes start playing (and loop if set)
            until stopped or the lights are changed manually.
            """
            return await scenes.apply(target_type, target_id, scene_id)

        @server.tool()
        def stop_scene(target_type: str = "all", target_id: int | None = None):
            """Stop sequence schemes playing on "all" lights, one "light", or a "group"."""
            return scenes.stop(target_type, target_id)

    def _register_schedule_tools(self) -> None:
        server = self.server

        def schedules():
            # Resolved when a tool runs, not at registration.
            return self.service.schedules

        @server.tool()
        def get_location():
            """The saved location for sunrise/sunset schedules, with today's sunrise and sunset (HH:MM)."""
            return schedules().location.today()

        @server.tool()
        def set_location(name: str, latitude: float, longitude: float):
            """Save the location (decimal latitude/longitude) used to compute sunrise and sunset."""
            schedules().location.save(LocationUpdate(name=name, latitude=latitude, longitude=longitude))
            return schedules().location.today()

        @server.tool()
        def list_schedules():
            """List schedules and alarms, each with its time today ("today_time", HH:MM).

            One-time schedules have a "run_date" and show the time on that date instead.
            """
            return schedules().list()

        @server.tool()
        def create_schedule(
            name: str,
            action: str,
            time_mode: str = "time",
            run_time: str | None = None,
            offset_minutes: int = 0,
            target_type: str = "all",
            target_id: int | None = None,
            scene_id: int | None = None,
            weekdays: list[int] | None = None,
            kind: str = "schedule",
            run_date: str | None = None,
        ):
            """Create a recurring or one-time schedule or alarm.

            action: "on", "off", or "scene" (with scene_id). time_mode: "time" (run_time
            "HH:MM"), "sunrise", or "sunset" (offset_minutes -180..180, e.g. -30 = 30 min
            before; needs set_location first). target_type: "all", "light", or "group"
            (rooms are groups) with target_id. weekdays: 0=Mon..6=Sun (default every day).
            run_date: "YYYY-MM-DD" to run once on that day instead of repeating (weekdays
            is then ignored); it must not have passed, and it switches off after running.
            """
            return schedules().add(
                ScheduleCreate(
                    name=name, action=action, time_mode=time_mode, run_time=run_time,
                    offset_minutes=offset_minutes, target_type=target_type, target_id=target_id,
                    scene_id=scene_id, weekdays=weekdays if weekdays is not None else list(range(7)),
                    kind=kind, run_date=run_date,
                )
            )

        @server.tool()
        def update_schedule(
            schedule_id: int,
            name: str | None = None,
            action: str | None = None,
            time_mode: str | None = None,
            run_time: str | None = None,
            offset_minutes: int | None = None,
            target_type: str | None = None,
            target_id: int | None = None,
            scene_id: int | None = None,
            weekdays: list[int] | None = None,
            kind: str | None = None,
            enabled: bool | None = None,
            run_date: str | None = None,
        ):
            """Edit a schedule or alarm (see list_schedules for ids); only the fields given change.

            Fields are as in create_schedule. enabled=False pauses it without deleting it.
            Switching time_mode to "time" needs a run_time; switching a target to "light" or
            "group" needs its target_id; switching action to "scene" needs a scene_id.
            run_date makes it one-time on that day (pass enabled=True to re-arm a one-time
            schedule that has run); weekdays without run_date makes it recurring again.
            """
            changes = {
                "name": name, "action": action, "time_mode": time_mode, "run_time": run_time,
                "offset_minutes": offset_minutes, "target_type": target_type, "target_id": target_id,
                "scene_id": scene_id, "weekdays": weekdays, "kind": kind, "enabled": enabled,
                "run_date": run_date,
            }
            current = schedules().get(schedule_id)
            fields = {field: current.get(field) for field in ScheduleCreate.model_fields}
            fields.update({field: value for field, value in changes.items() if value is not None})
            if weekdays is not None and run_date is None:
                fields["run_date"] = None
            return schedules().update(schedule_id, ScheduleCreate(**fields))

        @server.tool()
        def delete_schedule(schedule_id: int):
            """Delete a schedule or alarm."""
            schedules().delete(schedule_id)
            return {"deleted": True, "schedule_id": schedule_id}

    def _register_weather_tools(self) -> None:
        server = self.server

        def weather():
            # Resolved when a tool runs, not at registration.
            return self.service.weather

        @server.tool()
        def record_weather(
            periods: list[dict[str, Any]],
            day: str | None = None,
            location: str | None = None,
            summary: str | None = None,
            source: str | None = None,
        ):
            """Store a day's weather, replacing anything already saved for that day.

            Look up the forecast first (e.g. hourly or morning/afternoon/evening/night),
            then send it as periods. Each period: "start" ("HH:MM", local time) and
            "condition", plus optional "temperature_c", "precipitation_chance" (0-100),
            "cloud_cover" (0-100), "humidity" (0-100), "wind_kph", and "description".
            A period lasts until the next one starts; the first also covers earlier hours.
            condition is one of clear, partly_cloudy, cloudy, fog, rain, thunderstorm,
            snow (common words such as sunny, overcast, drizzle, mist, storm are mapped).
            day is "YYYY-MM-DD" (default today); summary is a short description of the day;
            source names where the data came from.
            """
            day_value = weather().day_or_today(day)
            return weather().record(
                WeatherReport(day=day_value, periods=periods, location=location, summary=summary, source=source)
            )

        @server.tool()
        def update_weather_period(
            start: str,
            condition: str | None = None,
            temperature_c: float | None = None,
            precipitation_chance: int | None = None,
            cloud_cover: int | None = None,
            humidity: int | None = None,
            wind_kph: float | None = None,
            description: str | None = None,
            day: str | None = None,
        ):
            """Change one weather period, matched by its start ("HH:MM"), or add it if new.

            Only the fields given change; other periods are kept. Use this when conditions
            change during the day (e.g. rain arrives earlier than forecast). A new period
            needs a condition. Creates the day's weather if none is saved yet.
            """
            changes = {
                "condition": condition, "temperature_c": temperature_c,
                "precipitation_chance": precipitation_chance, "cloud_cover": cloud_cover,
                "humidity": humidity, "wind_kph": wind_kph, "description": description,
            }
            return weather().update_period(
                day, start, {field: value for field, value in changes.items() if value is not None}
            )

        @server.tool()
        def get_weather(day: str | None = None):
            """Get saved weather. Without day: today's report, the weather and matching scheme
            right now ("now"), and the automation setting. With day ("YYYY-MM-DD"): that day's report.
            """
            return weather().today() if day is None else weather().get(day)

        @server.tool()
        def delete_weather(day: str):
            """Delete the weather saved for a day ("YYYY-MM-DD")."""
            weather().delete(day)
            return {"deleted": True, "day": day}

        @server.tool()
        def list_weather_schemes():
            """List the scheme used for each weather condition by day and by night.

            Day and night follow sunrise and sunset at the saved location (see
            set_location), or 06:00-18:00 without one. Every slot starts with a built-in
            "Weather · ..." scheme ("is_built_in"); set_weather_scheme changes it.
            """
            return weather().slot_list()

        @server.tool()
        def set_weather_scheme(condition: str, daypart: str, scheme_id: int):
            """Use a scheme for a weather condition by "day" or "night".

            To design a new look, create it first with create_solid_scheme or
            create_sequence_scheme (or change your own with update_*_scheme), then assign
            its id here. condition is as in record_weather.
            """
            slot = WeatherSlot(condition=condition, daypart=daypart)
            return weather().set_slot(slot.condition, slot.daypart, scheme_id)

        @server.tool()
        def reset_weather_schemes(condition: str | None = None, daypart: str | None = None):
            """Put weather slots back on their built-in schemes: one condition, one daypart,
            both, or (with neither) every slot."""
            if condition is not None:
                condition = WeatherSlot(condition=condition, daypart=daypart or "day").condition
            if daypart is not None:
                daypart = WeatherSlot(condition="clear", daypart=daypart).daypart
            return weather().reset_slots(condition, daypart)

        @server.tool()
        async def apply_weather_scheme(target_type: str = "all", target_id: int | None = None):
            """Apply the scheme for the weather right now to "all" lights, lights that are
            "on", one "light", or a "group" (rooms are groups). Needs today's weather saved."""
            return await weather().apply_current(target_type, target_id)

        @server.tool()
        def set_weather_automation(enabled: bool, target_type: str = "on", target_id: int | None = None):
            """Follow the weather automatically: each time today's weather changes period,
            day turns to night, or a slot's scheme changes, apply the matching scheme.

            target_type "on" (default) only changes lights that are already on, so lights
            are never switched on by the weather; "all", "light", or "group" (with
            target_id) apply to those lights and turn them on. It applies once per change,
            so a manual change stays until the next one.
            """
            return weather().set_automation(
                WeatherAutomationUpdate(enabled=enabled, target_type=target_type, target_id=target_id)
            )

    def _register_music_tools(self) -> None:
        server = self.server

        def music():
            # Resolved when a tool runs, not at registration.
            return self.service.music

        @server.tool()
        def get_music():
            """What Luna Vibia is playing now, its mood, the scheme for that mood, and the
            music automation setting.

            The mood comes from the track's tags, then its caption, checked in order:
            sleep, energetic, romantic, upbeat, melancholic, cozy, focus, then calm (also
            the fallback); "matched" lists the words that decided it, and "beat_depth"
            how hard that mood pulses when beats are on (see set_music_beats).
            """
            return music().now()

        @server.tool()
        def list_music_schemes():
            """List the scheme used for each music mood (sleep, calm, focus, cozy, romantic,
            melancholic, upbeat, energetic) and the words that mark each mood.

            Every mood starts with a built-in "Music · ..." scheme ("is_built_in"), e.g.
            soft light blues with minute-long fades for sleep; set_music_scheme changes it.
            """
            return music().slot_list()

        @server.tool()
        def set_music_scheme(mood: str, scheme_id: int):
            """Use a scheme for a music mood.

            To design a new look, create it first with create_solid_scheme or
            create_sequence_scheme (or change your own with update_*_scheme), then assign
            its id here. mood is one of those in list_music_schemes.
            """
            return music().set_slot(MusicSlot(mood=mood).mood, scheme_id)

        @server.tool()
        def reset_music_schemes(mood: str | None = None):
            """Put one music mood (or, without mood, every mood) back on its built-in scheme."""
            return music().reset_slots(None if mood is None else MusicSlot(mood=mood).mood)

        @server.tool()
        async def apply_music_scheme(target_type: str = "all", target_id: int | None = None, mood: str | None = None):
            """Apply the scheme for the mood of the track Luna Vibia is playing to "all" lights,
            lights that are "on", one "light", or a "group" (rooms are groups).

            Pass mood to light for one mood whether or not anything is playing (e.g. "sleep"
            when the user asks for sleep lighting).
            """
            return await music().apply_current(
                target_type, target_id, None if mood is None else MusicSlot(mood=mood).mood
            )

        @server.tool()
        def set_music_automation(enabled: bool, target_type: str = "on", target_id: int | None = None):
            """Follow the music: each time the track Luna Vibia plays changes mood (or that
            mood's scheme changes), apply the mood's scheme. Use it when the user wants the
            lights to match the music, e.g. alongside Vibia's play_tracks.

            target_type "on" (default) only changes lights that are already on; "all",
            "light", or "group" (with target_id) apply to those lights and turn them on.
            While music plays and lights follow it, weather automation pauses; when the
            music stops the lights stay as they are and the weather takes over again.
            """
            return music().set_automation(
                MusicAutomationUpdate(enabled=enabled, target_type=target_type, target_id=target_id)
            )

        @server.tool()
        def set_music_beats(enabled: bool, offset_ms: int | None = None, strength: float | None = None):
            """Pulse the lights on the beats of the music, in real time, while set_music_automation
            follows the music. Use it when the user wants the lights to move with the music.

            Each beat lifts the brightness and lets it fall before the next, in the colors
            of the mood's scheme, which move on every bar. How hard depends on the mood:
            energetic and upbeat music pulses strongly, cozy and romantic gently, calm and
            melancholic barely; sleep and focus never pulse and keep their smooth schemes.
            strength (0-2, default 1) scales every mood's pulse. offset_ms (-1000 to 3000,
            default 300) is how late the sound is heard after Vibia plays it, as Bluetooth
            speakers lag: if the lights flash before the beat, raise it; after, lower it.
            Settings not given stay as they are.
            """
            return music().set_beats(MusicBeatsUpdate(enabled=enabled, offset_ms=offset_ms, strength=strength))
