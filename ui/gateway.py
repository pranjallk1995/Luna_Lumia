"""The UI gateway: serves the React app, enforces sign-in, and fronts the backend.

The browser never sees the backend's API token. Every data route checks the
shared Luna session and this app's allowlist first, and only the routes the UI
uses are forwarded.
"""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from config import SSOConfig, UIConfig
from sso import CURRENT_USER, LunaSingleSignOn, send_user

ID = r"\d+"
# The backend routes the browser app may reach, as (method, path pattern).
PROXIED_ROUTES = tuple(
    (method, re.compile(pattern))
    for method, pattern in (
        ("GET", r"/api/dashboard"),
        ("POST", r"/api/discovery(/pc)?"),
        ("POST", r"/api/lights(/refresh)?"),
        ("PUT", rf"/api/lights/{ID}(/background)?"),
        ("DELETE", rf"/api/lights/{ID}"),
        ("POST", r"/api/control/(light|group|all|on)"),
        ("POST", r"/api/(rooms|groups)"),
        ("PUT", rf"/api/(rooms|groups)/{ID}"),
        ("DELETE", rf"/api/(rooms|groups)/{ID}"),
        ("POST", rf"/api/(rooms|groups)/{ID}/lights"),
        ("DELETE", rf"/api/(rooms|groups)/{ID}/lights/{ID}"),
        ("POST", r"/api/scenes(/stop)?"),
        ("PUT", rf"/api/scenes/{ID}"),
        ("DELETE", rf"/api/scenes/{ID}"),
        ("POST", rf"/api/scenes/{ID}/apply"),
        ("POST", r"/api/(transitions|schedules)"),
        ("PUT", rf"/api/(transitions|schedules)/{ID}"),
        ("DELETE", rf"/api/(transitions|schedules)/{ID}"),
        ("PUT", r"/api/location"),
    )
)
UNAVAILABLE = "Luna Lumia's backend is unavailable. Please try again."


class StaticApp(StaticFiles):
    """Serve the built app: hashed bundles are cached forever, the page itself never."""

    async def get_response(self, path: str, scope: Any) -> Response:
        response = await super().get_response(path, scope)
        immutable = path.startswith("assets/")
        response.headers["Cache-Control"] = UIConfig.IMMUTABLE_CACHE_CONTROL if immutable else "no-cache"
        return response


class UIGateway:
    """Translate browser requests into session checks and backend calls."""

    def __init__(
        self,
        config: UIConfig,
        backend_transport: httpx.AsyncBaseTransport | None = None,
        sso_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.config = config
        self.sso = LunaSingleSignOn(config.allowed_emails, config.sso, sso_transport, app="lumia")
        self.backend = httpx.AsyncClient(
            event_hooks={"request": [send_user]},
            base_url=config.api_url,
            headers={"Authorization": f"Bearer {config.api_token}"},
            timeout=UIConfig.API_TIMEOUT_SECONDS,
            transport=backend_transport,
        )

    # Sign-in

    @staticmethod
    def here(request: Request) -> str:
        """This app's public address. Behind a TLS-terminating proxy such as a Cloudflare
        tunnel, the proxy's X-Forwarded-Proto and X-Forwarded-Host give the real one."""
        headers = request.headers
        scheme = headers.get("x-forwarded-proto", "").split(",")[0].strip() or request.url.scheme
        host = headers.get("x-forwarded-host", "").split(",")[0].strip() or request.url.netloc
        return f"{scheme}://{host}/"

    async def person(self, request: Request) -> dict[str, Any] | None:
        return await self.sso.user(request.cookies.get(SSOConfig.COOKIE_NAME))

    def protected(self, handler: Callable[[Request], Awaitable[Response]]):
        """Run ``handler`` only for a signed-in person on this app's allowlist."""

        async def endpoint(request: Request) -> Response:
            user = await self.person(request)
            if user is None:
                return JSONResponse({"error": "Sign in to continue."}, status_code=401)
            if not self.sso.is_allowed(user):
                return JSONResponse({"error": "This account is not authorized."}, status_code=403)
            token = CURRENT_USER.set(user.get("user_id"))
            try:
                return await handler(request)
            finally:
                CURRENT_USER.reset(token)

        return endpoint

    async def session(self, request: Request) -> Response:
        """Tell the browser app who is signed in, with its settings once they are allowed."""
        here = self.here(request)
        user = await self.person(request)
        if user is None:
            return JSONResponse({"status": "signed_out", "login_url": self.sso.login_url(here)})
        logout_url = self.sso.logout_url(here)
        if not self.sso.is_allowed(user):
            return JSONResponse({"status": "forbidden", "email": user.get("email"), "logout_url": logout_url})
        return JSONResponse({"status": "signed_in", "email": user.get("email"), "logout_url": logout_url, "settings": self.settings()})

    @staticmethod
    def settings() -> dict[str, Any]:
        return {
            "version": UIConfig.VERSION,
            "preset_colors": UIConfig.PRESET_COLORS,
            "temperature_presets": UIConfig.TEMPERATURE_PRESETS,
            "weekday_names": UIConfig.WEEKDAY_NAMES,
            "min_color_temp": UIConfig.MIN_COLOR_TEMP,
            "max_color_temp": UIConfig.MAX_COLOR_TEMP,
            "default_color_temp": UIConfig.DEFAULT_COLOR_TEMP,
            "discovery_broadcast": UIConfig.DISCOVERY_BROADCAST,
            "name_max_chars": UIConfig.NAME_MAX_CHARS,
            "max_sequence_steps": UIConfig.MAX_SEQUENCE_STEPS,
        }

    # Backend

    async def proxy(self, request: Request) -> Response:
        path = request.url.path
        if not any(method == request.method and pattern.fullmatch(path) for method, pattern in PROXIED_ROUTES):
            return JSONResponse({"error": "Not found."}, status_code=404)
        body = await request.body()
        if len(body) > UIConfig.MAX_REQUEST_BYTES:
            return JSONResponse({"error": "This request is too large."}, status_code=413)
        try:
            response = await self.backend.request(
                request.method,
                path,
                params=request.query_params,
                content=body,
                headers={"Content-Type": request.headers.get("content-type", "application/json")},
            )
        except httpx.HTTPError:
            return JSONResponse({"error": UNAVAILABLE}, status_code=502)
        return Response(
            response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type"),
            headers={"Cache-Control": "no-store"},
        )

    # Application

    @staticmethod
    async def health(request: Request) -> Response:
        return JSONResponse({"status": "ok", "version": UIConfig.VERSION})

    def application(self) -> Starlette:
        app = Starlette(
            routes=[
                Route("/health", self.health),
                # Luna Unia's status page checks every app's UI at Streamlit's health path.
                Route("/_stcore/health", self.health),
                Route("/auth/session", self.session),
                Route("/api/{path:path}", self.protected(self.proxy), methods=["GET", "POST", "PUT", "DELETE"]),
                Mount("/", StaticApp(directory=UIConfig.STATIC_DIR, html=True, check_dir=False)),
            ]
        )

        async def secure_headers(request: Request, call_next) -> Response:
            response = await call_next(request)
            response.headers["Content-Security-Policy"] = UIConfig.CONTENT_SECURITY_POLICY
            response.headers["X-Content-Type-Options"] = "nosniff"
            return response

        app.add_middleware(BaseHTTPMiddleware, dispatch=secure_headers)
        return app


def create_app() -> Starlette:
    return UIGateway(UIConfig.from_env()).application()
