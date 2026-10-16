import asyncio
import unittest

from app.devices import LightController, WizDiscovery, WizLightAdapter
from app.models import LightState


class FakeRepository:
    def __init__(self): self.saved=[]
    def target_lights(self,target_type,target_id): return [{"id":1,"ip_address":"192.168.1.8","name":"Test"}]
    def update_state(self,light_id,**values): self.saved.append((light_id,values)); return {"id":light_id,**values}


class FakeAdapter:
    def __init__(self): self.calls=[]
    async def apply(self,ip_address,**state): self.calls.append((ip_address,state))


class DeviceTests(unittest.TestCase):
    def test_hex_to_rgb(self): self.assertEqual(WizLightAdapter.rgb("#12A0FF"),(18,160,255))
    def test_controller_applies_and_persists_state(self):
        repo,adapter=FakeRepository(),FakeAdapter()
        result=asyncio.run(LightController(repo,adapter).control("light",1,LightState(on=True,brightness=42,color="#123456")))
        self.assertTrue(result[0]["ok"]); self.assertEqual(adapter.calls[0][0],"192.168.1.8"); self.assertEqual(repo.saved[0][1]["brightness"],42)
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
