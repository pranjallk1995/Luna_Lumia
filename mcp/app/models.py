"""Validated request and command models for Luna Lumia."""

from datetime import time
from typing import ClassVar, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

CollectionKind = Literal["room", "group"]
ScheduleTarget = Literal["all", "light", "group"]
HEX_COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class Validators:
    """Reusable normalization rules shared by several models."""

    @staticmethod
    def image_url(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        if not cleaned.startswith(("http://", "https://")):
            raise ValueError("Image URL must use http or https")
        return cleaned

    @staticmethod
    def entity_name(value: str, entity: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError(f"{entity} name cannot be blank")
        if not all(character.isalnum() or character == " " for character in cleaned):
            raise ValueError(
                f"{entity} name may contain only letters, numbers, and spaces"
            )
        return cleaned

    @staticmethod
    def mac_address(value: str | None) -> str | None:
        if value is None:
            return None
        compact = value.replace(":", "").replace("-", "").strip().upper()
        if len(compact) != 12 or any(
            character not in "0123456789ABCDEF" for character in compact
        ):
            raise ValueError("Invalid MAC address")
        return ":".join(compact[index : index + 2] for index in range(0, 12, 2))


class LightNamed(BaseModel):
    """Base for payloads carrying a validated light name."""

    name: str = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return Validators.entity_name(value, "Light")


class CollectionNamed(BaseModel):
    """Base for payloads carrying a validated room or group name."""

    name: str = Field(min_length=1, max_length=30)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return Validators.entity_name(value, "Room/group")


class LightCreate(LightNamed):
    ip_address: str = Field(pattern=r"^(?:\d{1,3}\.){3}\d{1,3}$")
    protocol: Literal["wiz"] = "wiz"
    mac_address: str | None = Field(default=None, max_length=17)

    @field_validator("ip_address")
    @classmethod
    def valid_octets(cls, value: str) -> str:
        if any(int(part) > 255 for part in value.split(".")):
            raise ValueError("Invalid IPv4 address")
        return value

    @field_validator("mac_address")
    @classmethod
    def normalize_mac(cls, value: str | None) -> str | None:
        return Validators.mac_address(value)


class LightUpdate(LightNamed):
    pass


class LightState(BaseModel):
    """A partial light state; a bulb shows either an RGB color or a white temperature."""

    MIN_COLOR_TEMP: ClassVar[int] = 2200
    MAX_COLOR_TEMP: ClassVar[int] = 6500

    on: bool | None = None
    brightness: int | None = Field(default=None, ge=1, le=100)
    color: str | None = Field(default=None, pattern=HEX_COLOR_PATTERN)
    color_temp: int | None = Field(default=None, ge=MIN_COLOR_TEMP, le=MAX_COLOR_TEMP)

    @model_validator(mode="after")
    def one_color_mode(self):
        if self.color is not None and self.color_temp is not None:
            raise ValueError("Set either color or color_temp, not both")
        return self


class LightImageUpdate(BaseModel):
    image_url: str | None = Field(default=None, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def valid_image_url(cls, value: str | None) -> str | None:
        return Validators.image_url(value)


class RoomImageUpdate(BaseModel):
    room_key: str = Field(min_length=1, max_length=50, pattern=r"^[a-z0-9_-]+$")
    image_url: str = Field(min_length=1, max_length=2048)

    @field_validator("image_url")
    @classmethod
    def valid_image_url(cls, value: str) -> str:
        return Validators.image_url(value)  # type: ignore[return-value]


class GroupCreate(CollectionNamed):
    light_ids: list[int] = Field(min_length=1)


class GroupUpdate(CollectionNamed):
    pass


class GroupMembersUpdate(BaseModel):
    light_ids: list[int] = Field(min_length=1)


class SceneCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str = Field(pattern=HEX_COLOR_PATTERN)
    brightness: int = Field(ge=1, le=100)


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    kind: Literal["schedule", "alarm"] = "schedule"
    target_type: ScheduleTarget = "all"
    target_id: int | None = None
    action: Literal["on", "off", "scene"]
    scene_id: int | None = None
    run_time: time
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    enabled: bool = True

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if not value or any(day < 0 or day > 6 for day in value):
            raise ValueError("Choose at least one valid weekday")
        return sorted(set(value))

    @model_validator(mode="after")
    def valid_target_and_action(self):
        if self.target_type != "all" and self.target_id is None:
            raise ValueError("A light or group target is required")
        if self.action == "scene" and self.scene_id is None:
            raise ValueError("A color scheme is required")
        return self
