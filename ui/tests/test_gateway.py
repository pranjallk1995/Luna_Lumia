import unittest

import httpx
from starlette.testclient import TestClient

from config import SSOConfig, UIConfig
from gateway import UIGateway

OWNER = {"email": "owner@example.com", "email_verified": True}
STRANGER = {"email": "other@example.com", "email_verified": True}
TOKEN = "t" * 32


class GatewayTestCase(unittest.TestCase):
    def setUp(self):
        self.backend_requests: list[httpx.Request] = []
        self.backend_error = False

        def sso(request: httpx.Request) -> httpx.Response:
            session = {"owner": OWNER, "stranger": STRANGER}.get(request.headers["X-Luna-Session"])
            return httpx.Response(200, json=session) if session else httpx.Response(401)

        def backend(request: httpx.Request) -> httpx.Response:
            if self.backend_error:
                raise httpx.ConnectError("down", request=request)
            self.backend_requests.append(request)
            return httpx.Response(200, json={"status": "ok"})

        config = UIConfig(
            api_url="http://backend",
            api_token=TOKEN,
            allowed_emails=frozenset({"owner@example.com"}),
            sso=SSOConfig(public_url="https://auth.example.com"),
        )
        self.gateway = UIGateway(config, httpx.MockTransport(backend), httpx.MockTransport(sso))
        self.client = TestClient(self.gateway.application(), base_url="https://app.example.com")

    def sign_in(self, who: str = "owner") -> None:
        self.client.cookies.set(SSOConfig.COOKIE_NAME, who)


class SessionTests(GatewayTestCase):
    def test_signed_out_gets_a_login_link_back_to_this_app(self):
        session = self.client.get("/auth/session").json()
        self.assertEqual(session["status"], "signed_out")
        self.assertEqual(session["login_url"], "https://auth.example.com/login?next=https%3A%2F%2Fapp.example.com%2F")

    def test_forwarded_headers_give_the_public_address(self):
        session = self.client.get(
            "/auth/session", headers={"X-Forwarded-Proto": "https", "X-Forwarded-Host": "public.example.com"}
        ).json()
        self.assertIn("next=https%3A%2F%2Fpublic.example.com%2F", session["login_url"])

    def test_allowed_person_is_signed_in_and_never_sees_the_api_token(self):
        self.sign_in()
        response = self.client.get("/auth/session")
        self.assertEqual(response.json()["status"], "signed_in")
        self.assertNotIn(TOKEN, response.text)

    def test_unlisted_person_is_forbidden(self):
        self.sign_in("stranger")
        self.assertEqual(self.client.get("/auth/session").json()["status"], "forbidden")


class ProxyTests(GatewayTestCase):
    def test_data_needs_an_allowed_session(self):
        self.assertEqual(self.client.get("/api/dashboard").status_code, 401)
        self.sign_in("stranger")
        self.assertEqual(self.client.get("/api/dashboard").status_code, 403)
        self.assertEqual(self.backend_requests, [])

    def test_allowed_route_carries_the_token_and_the_query(self):
        self.sign_in()
        response = self.client.get("/api/dashboard?x=1")
        self.assertEqual(response.status_code, 200)
        sent = self.backend_requests[0]
        self.assertEqual(sent.headers["Authorization"], f"Bearer {TOKEN}")
        self.assertEqual(sent.url.params["x"], "1")

    def test_creating_is_forwarded_with_its_body(self):
        self.sign_in()
        self.client.post("/api/control/light", json={"target_id": 1, "state": {"on": True}})
        self.assertEqual(self.backend_requests[0].url.path, "/api/control/light")
        self.assertIn(b"target_id", self.backend_requests[0].content)

    def test_routes_the_ui_does_not_use_are_not_forwarded(self):
        self.sign_in()
        for method, path in (
            ("POST", "/api/control/everything"),
            ("PUT", "/api/room-image"),
            ("GET", "/api/lights"),
            ("DELETE", "/api/lights/refresh"),
            ("DELETE", "/api/scenes/stop"),
        ):
            self.assertEqual(self.client.request(method, path).status_code, 404, path)
        self.assertEqual(self.backend_requests, [])

    def test_unreachable_backend_is_a_clear_error(self):
        self.sign_in()
        self.backend_error = True
        response = self.client.get("/api/dashboard")
        self.assertEqual(response.status_code, 502)
        self.assertIn("unavailable", response.json()["error"])

    def test_every_change_the_ui_makes_is_forwarded(self):
        self.sign_in()
        for method, path in (
            ("POST", "/api/discovery"),
            ("POST", "/api/lights/refresh"),
            ("PUT", "/api/lights/3"),
            ("PUT", "/api/lights/3/background"),
            ("DELETE", "/api/lights/3"),
            ("POST", "/api/control/on"),
            ("POST", "/api/rooms/2/lights"),
            ("DELETE", "/api/groups/2/lights/3"),
            ("POST", "/api/scenes/4/apply"),
            ("POST", "/api/scenes/stop"),
            ("PUT", "/api/transitions/5"),
            ("DELETE", "/api/schedules/6"),
            ("PUT", "/api/location"),
        ):
            self.assertEqual(self.client.request(method, path).status_code, 200, path)

    def test_settings_reach_the_browser_app(self):
        self.sign_in()
        settings = self.client.get("/auth/session").json()["settings"]
        self.assertEqual(settings["max_color_temp"], UIConfig.MAX_COLOR_TEMP)
        self.assertEqual(settings["preset_colors"], UIConfig.PRESET_COLORS)

    def test_oversized_body_is_refused(self):
        self.sign_in()
        response = self.client.post("/api/lights", content=b"x" * (UIConfig.MAX_REQUEST_BYTES + 1))
        self.assertEqual(response.status_code, 413)


class ApplicationTests(GatewayTestCase):
    def test_health_needs_no_session_on_both_paths(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        self.assertEqual(self.client.get("/_stcore/health").status_code, 200)

    def test_security_headers(self):
        headers = self.client.get("/health").headers
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")


if __name__ == "__main__":
    unittest.main()
