"""UI-facing client for Luna Lumia's HTTP routes."""

from typing import Any

import httpx

from config import UIConfig


class LumiaAPI:
    """Keep backend routes and HTTP details out of Streamlit views."""

    def __init__(self, config: UIConfig) -> None:
        self.base_url = config.api_url
        self.timeout = config.api_timeout

    def request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = httpx.request(
            method, f"{self.base_url}{path}", timeout=self.timeout, **kwargs
        )
        response.raise_for_status()
        return None if response.status_code == 204 else response.json()

    def dashboard(self) -> dict[str, Any]:
        return self.request("GET", "/api/dashboard")

    def discover(self, broadcast_space: str) -> list[dict[str, Any]]:
        return self.request(
            "POST", "/api/discovery", json={"broadcast_space": broadcast_space}
        )

    def create(self, resource: str, payload: dict) -> dict[str, Any]:
        return self.request("POST", f"/api/{resource}", json=payload)

    def update(self, resource: str, item_id: int, payload: dict) -> dict[str, Any]:
        return self.request("PUT", f"/api/{resource}/{item_id}", json=payload)

    def delete(self, resource: str, item_id: int) -> None:
        self.request("DELETE", f"/api/{resource}/{item_id}")

    def control(self, target_type: str, target_id: int | None = None, **state: Any):
        return self.request(
            "POST",
            f"/api/control/{target_type}",
            json={"target_id": target_id, "state": state},
        )

    def apply_scene(self, scene_id: int, target_type: str = "all", target_id: int | None = None):
        return self.request(
            "POST",
            f"/api/scenes/{scene_id}/apply",
            json={"target_type": target_type, "target_id": target_id},
        )

    def rename_light(self, light_id: int, name: str) -> dict[str, Any]:
        """Rename a light, then re-infer its background from the new name."""
        self.update("lights", light_id, {"name": name})
        return self.set_light_background(light_id)

    def set_light_background(self, light_id: int, image_url: str | None = None):
        return self.request(
            "PUT", f"/api/lights/{light_id}/background", json={"image_url": image_url}
        )

    def update_room_image(self, room_key: str, image_url: str):
        return self.request(
            "PUT", "/api/room-image", json={"room_key": room_key, "image_url": image_url}
        )

    def add_collection_lights(self, kind: str, collection_id: int, light_ids: list[int]):
        return self.request(
            "POST", f"/api/{kind}s/{collection_id}/lights", json={"light_ids": light_ids}
        )

    def remove_collection_light(self, kind: str, collection_id: int, light_id: int) -> None:
        self.request("DELETE", f"/api/{kind}s/{collection_id}/lights/{light_id}")
