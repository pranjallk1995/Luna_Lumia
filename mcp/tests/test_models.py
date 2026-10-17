import unittest
from pydantic import ValidationError
from app.models import GroupCreate, GroupMembersUpdate, GroupUpdate, LightCreate, LightImageUpdate, LightState, LightUpdate, RoomImageUpdate, ScheduleCreate
from app.room_images import ImageScheme, RoomKeyDetector


class ModelTests(unittest.TestCase):
    def test_rejects_invalid_ipv4_octet(self):
        with self.assertRaises(ValidationError): LightCreate(name="Bad",ip_address="192.168.1.999")
    def test_scene_schedule_requires_scene(self):
        with self.assertRaises(ValidationError): ScheduleCreate(name="Wake",action="scene",run_time="07:00",weekdays=[0])
    def test_normalizes_discovered_mac_address(self):
        light=LightCreate(name="Bulb",ip_address="192.168.1.8",mac_address="9877d5b72872")
        self.assertEqual(light.mac_address,"98:77:D5:B7:28:72")
    def test_light_name_is_trimmed(self):
        self.assertEqual(LightUpdate(name="  Kitchen  ").name,"Kitchen")
    def test_light_and_room_names_reject_symbols_and_emoji(self):
        with self.assertRaises(ValidationError): LightUpdate(name="Kitchen 💡")
        with self.assertRaises(ValidationError): LightCreate(name="Desk@Home",ip_address="192.168.1.8")
        with self.assertRaises(ValidationError): GroupCreate(name="Bedroom!",light_ids=[1])
    def test_light_and_room_names_are_limited_to_thirty_characters(self):
        with self.assertRaises(ValidationError): LightUpdate(name="L" * 31)
        with self.assertRaises(ValidationError): GroupCreate(name="R" * 31,light_ids=[1])
        with self.assertRaises(ValidationError): GroupUpdate(name="R" * 31)
    def test_light_background_requires_http_url(self):
        with self.assertRaises(ValidationError): LightImageUpdate(image_url="file:///private/room.png")
    def test_room_image_accepts_visia_url(self):
        entry=RoomImageUpdate(room_key="living_room",image_url="https://visia.example/api/public/images/123")
        self.assertEqual(entry.room_key,"living_room")
    def test_public_room_images_share_a_scheme_key(self):
        first=ImageScheme.key("https://visia.example/api/public/images/123")
        second=ImageScheme.key("https://visia.example/api/public/images/456")
        self.assertEqual(first,second)
    def test_room_key_can_be_inferred_from_member_light_name(self):
        self.assertIsNone(RoomKeyDetector.detect("Downstairs"))
        self.assertEqual(RoomKeyDetector.detect("Kitchen ceiling"),"kitchen")
    def test_group_requires_name_and_at_least_one_light(self):
        with self.assertRaises(ValidationError): GroupCreate(name="",light_ids=[1])
        with self.assertRaises(ValidationError): GroupCreate(name="Kitchen",light_ids=[])
        with self.assertRaises(ValidationError): GroupMembersUpdate(light_ids=[])
    def test_color_temp_is_bounded_and_exclusive_with_color(self):
        self.assertEqual(LightState(color_temp=2700).color_temp,2700)
        with self.assertRaises(ValidationError): LightState(color_temp=1800)
        with self.assertRaises(ValidationError): LightState(color="#FFFFFF",color_temp=2700)
