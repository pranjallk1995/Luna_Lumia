import os
from pathlib import Path


class UIConfig:
    API_URL = os.getenv("LUNALUMIA_API_URL", "http://127.0.0.1:18002").rstrip("/")
    UI_ROOT = Path(__file__).resolve().parent
    LOGO_PATH = UI_ROOT / "assets" / "lunalumia_logo.png"
    PRESET_COLORS = (
        "#F5F5F5",
        "#FFBE55",
        "#FF836A",
        "#B86DE0",
    )
