import os
import unittest
from unittest.mock import MagicMock, patch

from mcp.server.fastmcp import FastMCP
from starlette.testclient import TestClient

from app.branding import ServerBranding
from app.config import AppConfig
from app.http_routes import LumiaHTTPRoutes


class APIAuthenticationTests(unittest.TestCase):
    TOKEN = "test-token-that-is-at-least-32-characters"

    def setUp(self):
        server = FastMCP("Luna Lumia")
        service = MagicMock()
        service.dashboard.return_value = {"lights": []}
        LumiaHTTPRoutes(server, service, ServerBranding(), self.TOKEN)
        self.client = TestClient(server.streamable_http_app())
        self.service = service

    def test_api_rejects_missing_and_incorrect_credentials(self):
        missing = self.client.get("/api/dashboard")
        incorrect = self.client.get(
            "/api/dashboard", headers={"Authorization": "Bearer wrong"}
        )
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(incorrect.status_code, 401)
        self.assertEqual(missing.headers["www-authenticate"], "Bearer")
        self.assertEqual(missing.headers["cache-control"], "no-store")
        self.service.dashboard.assert_not_called()

    def test_api_accepts_shared_bearer_credential(self):
        response = self.client.get(
            "/api/dashboard", headers={"Authorization": f"Bearer {self.TOKEN}"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"lights": []})
        self.service.dashboard.assert_called_once_with()

    def test_health_and_icons_remain_public(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/favicon.ico").status_code, 200)


class AuthenticationConfigTests(unittest.TestCase):
    def test_api_token_is_required_and_must_be_long(self):
        base = {"DATABASE_URL": "postgresql://example"}
        with patch.dict(os.environ, base, clear=True):
            with self.assertRaisesRegex(RuntimeError, "LUNALUMIA_API_TOKEN"):
                AppConfig.from_env()
        with patch.dict(os.environ, {**base, "LUNALUMIA_API_TOKEN": "short"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "at least 32"):
                AppConfig.from_env()

    def test_valid_api_token_is_loaded(self):
        with patch.dict(
            os.environ,
            {"DATABASE_URL": "postgresql://example", "LUNALUMIA_API_TOKEN": "x" * 32},
            clear=True,
        ):
            self.assertEqual(AppConfig.from_env().api_token, "x" * 32)


if __name__ == "__main__":
    unittest.main()
