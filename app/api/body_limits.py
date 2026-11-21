"""Bound JSON request buffering before authentication and body parsing."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit = get_settings().fikrah_request_max_bytes
        headers = dict(scope.get("headers", []))
        length = headers.get(b"content-length")
        if length is not None:
            try:
                too_large = int(length) > limit
            except ValueError:
                too_large = True
            if too_large:
                await JSONResponse(
                    {"detail": "Request body is too large"}, status_code=413
                )(scope, receive, send)
                return
        chunks = []
        size = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > limit:
                await JSONResponse(
                    {"detail": "Request body is too large"}, status_code=413
                )(scope, receive, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = b"".join(chunks)
        sent_body = False

        async def buffered_receive():
            nonlocal sent_body
            if sent_body:
                return await receive()
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}

        await self.app(scope, buffered_receive, send)
