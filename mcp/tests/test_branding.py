import base64
import unittest
from unittest.mock import MagicMock

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from app.branding import ServerBranding
from app.http_routes import LumiaHTTPRoutes


class BrandingTests(unittest.TestCase):
    def test_server_info_icons_are_embedded_pngs(self):
        icons = ServerBranding().mcp_icons()
        self.assertEqual([icon.sizes for icon in icons], [["48x48"], ["96x96"]])
        header, data = icons[0].src.split(",", 1)
        self.assertEqual(header, "data:image/png;base64")
        self.assertTrue(base64.b64decode(data).startswith(b"\x89PNG"))

    def test_only_bundled_icons_resolve(self):
        branding = ServerBranding()
        self.assertTrue(branding.icon_path("icon-512.png").is_file())
        self.assertTrue(branding.favicon_path().is_file())
        with self.assertRaises(FileNotFoundError):
            branding.icon_path("../main.py")

    def test_icons_are_served_over_http(self):
        branding = ServerBranding()
        server = FastMCP("Luna Lumia", icons=branding.mcp_icons())
        LumiaHTTPRoutes(server, MagicMock(), branding, "t" * 32)
        client = TestClient(server.streamable_http_app())
        favicon = client.get("/favicon.ico")
        self.assertEqual((favicon.status_code, favicon.headers["content-type"]), (200, "image/x-icon"))
        self.assertEqual(client.get("/icons/icon-192.png").headers["content-type"], "image/png")
        self.assertEqual(client.get("/icons/missing.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
