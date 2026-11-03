"""The lights are on the owner's network: nobody else can reach them or see what they show."""

import asyncio
import unittest
from unittest import mock

from app.core import tenancy
from app.services.application import LightService
from app.services.playback import OwnerScenes


class OwnerSceneTests(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = mock.Mock()
        self.engine.playing.return_value = {1: 2}
        self.engine.live.return_value = {1: {"color": "#FFFFFF"}}
        self.engine.beats_playing.return_value = True
        self.scenes = OwnerScenes(self.engine)

    def test_others_neither_see_nor_change_what_plays(self) -> None:
        with tenancy.acting_as("ab12"):
            self.assertEqual((self.scenes.playing(), self.scenes.live()), ({}, {}))
            self.assertFalse(self.scenes.beats_playing())
            self.scenes.stop([1])
            self.scenes.play(1, [], False, [{"id": 1}])
        self.engine.stop.assert_not_called()
        self.engine.play.assert_not_called()

    def test_the_owner_controls_it(self) -> None:
        with tenancy.acting_as(tenancy.OWNER):
            self.assertEqual(self.scenes.playing(), {1: 2})
            self.scenes.stop([1])
        self.engine.stop.assert_called_once_with([1])


class OwnerDeviceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.discovery, self.repository = mock.Mock(), mock.Mock()
        self.lights = LightService(self.repository, self.discovery, mock.Mock(), mock.Mock(), mock.Mock())

    def test_others_cannot_scan_the_network_or_add_devices(self) -> None:
        with tenancy.acting_as("ab12"):
            with self.assertRaises(PermissionError):
                asyncio.run(self.lights.discover())
            with self.assertRaises(PermissionError):
                asyncio.run(self.lights.discover_pc("192.168.1.15"))
            with self.assertRaises(PermissionError):
                asyncio.run(self.lights.discover_openrgb("192.168.1.15"))
            with self.assertRaises(PermissionError):
                asyncio.run(self.lights.discover_icue("192.168.1.15"))
            with self.assertRaises(PermissionError):
                self.lights.add(mock.Mock())
        self.discovery.discover.assert_not_called()
        self.repository.add.assert_not_called()
