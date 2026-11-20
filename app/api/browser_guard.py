"""Protect a local API from untrusted browser hosts and state-changing origins."""

from collections.abc import Iterable
from urllib.parse import urlsplit

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class BrowserGuard:
    def __init__(self, app: ASGIApp, allowed_hosts: Iterable[str], allowed_origins: Iterable[str]) -> None:
        self.app = app
        self.hosts = frozenset(host.strip().lower().strip("[]") for host in allowed_hosts if host.strip())
        self.origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        authorities = headers.getlist("host")
        authority = authorities[0] if len(authorities) == 1 else ""
        try:
            host = urlsplit(f"//{authority}")
            valid_host = (host.hostname in self.hosts and host.username is None and host.password is None
                          and not (host.path or host.query or host.fragment))
            port = host.port
        except ValueError:
            valid_host = False
            port = None
        if not valid_host:
            await JSONResponse({"detail": "Unrecognized API host."}, status_code=400)(scope, receive, send)
            return
        if scope["method"] not in SAFE_METHODS:
            origin = headers.get("origin")
            same_origin = f"{scope['scheme']}://{authority.lower()}"
            if (scope["scheme"], port) in {("http", 80), ("https", 443)}:
                same_origin = same_origin.rsplit(":", 1)[0]
            if (origin is not None and origin not in self.origins and origin != same_origin) or (
                origin is None and headers.get("sec-fetch-site") == "cross-site"
            ):
                await JSONResponse({"detail": "This browser origin cannot change the library."}, status_code=403)(
                    scope, receive, send,
                )
                return
        await self.app(scope, receive, send)
