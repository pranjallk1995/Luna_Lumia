"""Turn Lumia light states into one RGB color, for PC devices that have no brightness of their own."""

from dataclasses import dataclass, field


@dataclass
class SolidColors:
    """Last color/brightness per device, so a brightness-only or power-on command keeps its color."""

    memory: dict[str, dict] = field(default_factory=dict)

    @staticmethod
    def rgb(hex_color: str) -> tuple[int, int, int]:
        value = hex_color.lstrip("#")
        return tuple(int(value[index : index + 2], 16) for index in (0, 2, 4))

    @staticmethod
    def white(kelvin: int) -> tuple[int, int, int]:
        from app.services.playback import ColorMath  # local import: services depend on integrations

        return ColorMath.kelvin_to_rgb(kelvin)

    def remembered(self, key: str) -> dict:
        return self.memory.setdefault(key, {"rgb": (255, 255, 255), "brightness": 100})

    def target(self, key: str, *, on, brightness, color, color_temp) -> tuple[int, int, int]:
        remembered = self.remembered(key)
        if color is not None:
            remembered["rgb"] = self.rgb(color)
        elif color_temp is not None:
            remembered["rgb"] = self.white(color_temp)
        if brightness is not None:
            remembered["brightness"] = brightness
        if on is False or not any(remembered["rgb"]):
            return (0, 0, 0)
        scale = remembered["brightness"] / 100
        return tuple(round(channel * scale) for channel in remembered["rgb"])
