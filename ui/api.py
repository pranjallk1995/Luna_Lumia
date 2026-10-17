from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class LumiaAPI:
    base_url: str
    timeout: float = 8.0

    def request(self, method, path, **kwargs):
        response=httpx.request(method,f"{self.base_url}{path}",timeout=self.timeout,**kwargs)
        response.raise_for_status()
        return None if response.status_code == 204 else response.json()
    def dashboard(self): return self.request("GET","/api/dashboard")
    def discover(self, broadcast_space="192.168.1.255"):
        return self.request("POST","/api/discovery",json={"broadcast_space":broadcast_space})
    def create(self, resource, payload): return self.request("POST",f"/api/{resource}",json=payload)
    def update(self, resource, item_id, payload): return self.request("PUT",f"/api/{resource}/{item_id}",json=payload)
    def delete(self, resource, item_id): return self.request("DELETE",f"/api/{resource}/{item_id}")
    def control(self, target_type, target_id=None, **state): return self.request("POST",f"/api/control/{target_type}",json={"target_id":target_id,"state":state})
    def apply_scene(self, scene_id, target_type="all", target_id=None): return self.request("POST",f"/api/scenes/{scene_id}/apply",json={"target_type":target_type,"target_id":target_id})
    def set_light_background(self, light_id, image_url=None): return self.request("PUT",f"/api/lights/{light_id}/background",json={"image_url":image_url})
    def update_room_image(self, room_key, image_url): return self.request("PUT","/api/room-image",json={"room_key":room_key,"image_url":image_url})
    def add_room_lights(self, room_id, light_ids): return self.request("POST",f"/api/rooms/{room_id}/lights",json={"light_ids":light_ids})
    def remove_room_light(self, room_id, light_id): return self.request("DELETE",f"/api/rooms/{room_id}/lights/{light_id}")
    def add_group_lights(self, group_id, light_ids): return self.request("POST",f"/api/groups/{group_id}/lights",json={"light_ids":light_ids})
    def remove_group_light(self, group_id, light_id): return self.request("DELETE",f"/api/groups/{group_id}/lights/{light_id}")
