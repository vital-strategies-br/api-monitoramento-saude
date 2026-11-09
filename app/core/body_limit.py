from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core import messages
from app.core.config import settings
from app.utils.http import error_response, is_public_request


class BodySizeLimitMiddleware:
    """Rejects bodies above MAX_REQUEST_BODY_BYTES with 413 before anything reads them.

    Runs before ApiAuthMiddleware, which loads the whole body to verify the HMAC.
    Checks the declared Content-Length first, then counts the bytes actually
    received, so chunked bodies or a false Content-Length are also caught.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or is_public_request(scope["method"], scope["path"]):
            await self.app(scope, receive, send)
            return

        limit = settings.MAX_REQUEST_BODY_BYTES
        too_large = error_response(413, messages.BODY_TOO_LARGE.format(max_bytes=limit))

        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > limit:
            await too_large(scope, receive, send)
            return

        body = bytearray()
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > limit:
                await too_large(scope, receive, send)
                return
            more_body = message.get("more_body", False)

        await self.app(scope, _replay(bytes(body), receive), send)


def _replay(body: bytes, receive: Receive) -> Receive:
    """Hand the buffered body downstream once, then defer to the real channel."""
    delivered = False

    async def replay() -> Message:
        nonlocal delivered
        if delivered:
            return await receive()
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return replay
