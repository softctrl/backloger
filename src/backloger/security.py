"""Local HTTP boundary: Host/Origin checks, mutation token and bounded bodies."""

import secrets

from starlette.datastructures import URL, Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

BODY_LIMIT = 256 * 1024


class LocalSecurity:
    def __init__(self, app: ASGIApp, token: str):
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        origin = headers.get("origin")
        url = URL(scope=scope)
        valid_origin = f"{url.scheme}://{url.netloc}"
        problem: tuple[int, str] | None = None
        if headers.get("sec-fetch-site") == "cross-site" or (origin and origin != valid_origin):
            problem = (403, "Origem não autorizada")
        elif scope["method"] not in {"GET", "HEAD", "OPTIONS"} and not secrets.compare_digest(
            headers.get("x-backloger-token", ""),
            self.token,
        ):
            problem = (403, "Token de proteção CSRF inválido")
        if problem:
            await JSONResponse(
                {"error": "forbidden", "message": problem[1]}, status_code=problem[0]
            )(scope, receive, send)
            return
        # Buffer at the HTTP boundary so chunked bodies cannot bypass the cap.
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > BODY_LIMIT:
                await JSONResponse({"error": "body_too_large"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        async def secured_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                frame_policy = b"'self'" if scope.get("path") == "/document" else b"'none'"
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"no-referrer"),
                    (b"cache-control", b"no-store"),
                    (
                        b"content-security-policy",
                        b"default-src 'self'; script-src 'self'; "
                        b"style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                        b"connect-src 'self'; object-src 'none'; base-uri 'none'; "
                        b"frame-ancestors " + frame_policy + b"; form-action 'self'",
                    ),
                ]
            await send(message)

        await self.app(scope, replay, secured_send)
