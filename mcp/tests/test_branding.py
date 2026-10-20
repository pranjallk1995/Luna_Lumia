import base64
import unittest
from unittest.mock import MagicMock

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from app.transport.branding import ServerBranding
from app.transport.http_routes import LumiaHTTPRoutes


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

    def test_public_url_icons_are_listed_before_embedded_ones(self):
        icons = ServerBranding("https://mcp.example.com/").mcp_icons()
        self.assertEqual(
            [icon.src for icon in icons[:4]],
            [f"https://mcp.example.com/icons/icon-{size}.png" for size in ServerBranding.ICON_SIZES],
        )
        self.assertTrue(icons[4].src.startswith("data:image/png;base64,"))

    def test_home_page_links_the_icons(self):
        branding = ServerBranding()
        server = FastMCP("test", icons=branding.mcp_icons())
        LumiaHTTPRoutes(server, MagicMock(), branding, "t" * 32)
        page = TestClient(server.streamable_http_app()).get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("text/html", page.headers["content-type"])
        self.assertIn('href="/icons/icon-192.png"', page.text)
        self.assertIn('href="/favicon.ico"', page.text)

if __name__ == "__main__":
    unittest.main()
