import unittest
from pydantic import ValidationError
from app.models import LightCreate, LightUpdate, ScheduleCreate


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
