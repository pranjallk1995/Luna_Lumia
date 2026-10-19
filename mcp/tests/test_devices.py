import asyncio
import unittest

from app.devices import WizDiscovery, WizLightAdapter
from app.models import LightState
from app.services import LightControlService


class FakeRepository:
    def __init__(self): self.saved=[]
    def targets(self,target_type,target_id): return [{"id":1,"ip_address":"192.168.1.8","name":"Test"}]
    def update_state(self,light_id,**values): self.saved.append((light_id,values)); return {"id":light_id,**values}


class FakeAdapter:
    def __init__(self): self.calls=[]
    async def apply(self,ip_address,**state): self.calls.append((ip_address,state))
    async def status(self,ip_address):
        self.calls.append((ip_address,"status"))
        return {"mac_address":None,"on":True,"brightness":64,"color":"#AABBCC"}


class DeviceTests(unittest.TestCase):
    def test_hex_to_rgb(self): self.assertEqual(WizLightAdapter.rgb("#12A0FF"),(18,160,255))
    def test_controller_applies_and_persists_state(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        result=asyncio.run(LightControlService(repo,adapter).control("light",1,LightState(on=True,brightness=42,color="#123456")))
        self.assertTrue(result[0]["ok"]); self.assertEqual(adapter.calls[0][0],"192.168.1.8"); self.assertEqual(repo.saved[0][1]["brightness"],42)
    def test_controller_polls_and_persists_status(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        result=asyncio.run(LightControlService(repo,adapter).poll_statuses())
        self.assertTrue(result[0]["ok"])
        self.assertEqual(repo.saved[0][1],{"on":True,"brightness":64,"color":"#AABBCC","reachable":True})
    def test_discovery_shape(self):
        discovery=WizDiscovery()
        async def fake_probe(ip_address):
            if ip_address != "192.168.1.8": return None
            return {"ip_address":ip_address,"mac_address":"AA:BB:CC:DD:EE:FF","protocol":"wiz"}
        discovery._probe=fake_probe
        result=asyncio.run(discovery.scan("192.168.1.255"))
        self.assertEqual(result,[{"ip_address":"192.168.1.8","mac_address":"AA:BB:CC:DD:EE:FF","protocol":"wiz"}])
    def test_discovery_ignores_refused_addresses(self):
        discovery=WizDiscovery()
        async def refusing_probe(ip_address):
            if ip_address.endswith(".8"):
                return {"ip_address":ip_address,"mac_address":None,"protocol":"wiz"}
            raise ConnectionRefusedError(111,"Connection refused")
        discovery._probe=refusing_probe
        result=asyncio.run(discovery.scan("192.168.1.255"))
        self.assertEqual([item["ip_address"] for item in result],["192.168.1.8"])
    def test_reported_color_temp_is_clamped(self):
        self.assertEqual(WizLightAdapter.clamp_color_temp(10000),6500)
        self.assertEqual(WizLightAdapter.clamp_color_temp(2700),2700)
        self.assertIsNone(WizLightAdapter.clamp_color_temp(None))
    def test_controller_forwards_and_persists_color_temp(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        asyncio.run(LightControlService(repo,adapter).control("light",1,LightState(color_temp=3000)))
        self.assertEqual(adapter.calls[0][1]["color_temp"],3000); self.assertEqual(repo.saved[0][1]["color_temp"],3000)
    def test_on_target_needs_no_id(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        asyncio.run(LightControlService(repo,adapter).control("on",None,LightState(color_temp=3000)))
        self.assertIsNone(adapter.calls[0][1]["on"])
    def test_color_change_records_light_as_on_without_sending_off(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        asyncio.run(LightControlService(repo,adapter).control("light",1,LightState(color="#FF0000")))
        self.assertIsNone(adapter.calls[0][1]["on"])
        self.assertTrue(repo.saved[0][1]["on"])
    def test_poll_flags_a_different_bulb_answering_at_a_lights_ip(self):
        class Repo(FakeRepository):
            def targets(self,target_type,target_id):
                return [{"id":13,"ip_address":"192.168.1.9","name":"Bedroom","mac_address":"98:77:D5:D6:9E:A2"}]
        class SwappedAdapter(FakeAdapter):
            async def status(self,ip_address):
                return {"mac_address":"9877d5d6d5fe","on":False,"brightness":10,"color":None}
        repo=Repo()
        result=asyncio.run(LightControlService(repo,SwappedAdapter()).poll_statuses())
        self.assertTrue(result[0]["moved"]); self.assertFalse(result[0]["ok"])
        self.assertEqual(repo.saved,[])  # the other bulb's state is not written onto this light
    def test_poll_accepts_matching_mac_in_any_format(self):
        class Repo(FakeRepository):
            def targets(self,target_type,target_id):
                return [{"id":1,"ip_address":"192.168.1.8","name":"A","mac_address":"98:77:D5:D6:D5:FE"}]
        class Adapter(FakeAdapter):
            async def status(self,ip_address):
                return {"mac_address":"9877d5d6d5fe","on":True,"brightness":50,"color":None}
        repo=Repo()
        self.assertTrue(asyncio.run(LightControlService(repo,Adapter()).poll_statuses())[0]["ok"])
        self.assertNotIn("mac_address",repo.saved[0][1])
