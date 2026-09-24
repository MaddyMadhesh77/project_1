from __future__ import annotations

import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


class UnhandledErrorMiddleware:
    """Turns an uncaught exception into a generic JSON 500.

    This used to be an `@app.exception_handler(Exception)`, but Starlette runs
    that handler in ServerErrorMiddleware -- outside every user middleware,
    CORS included -- so the 500 went out without Access-Control-Allow-Origin
    and the browser reported an opaque network error instead of a server
    error. As a middleware registered inside CORS, the 500 gets CORS headers
    like any other response.

    Logs the full traceback server-side and never echoes str(exc), which can
    leak internals (a raw SQL error, a file path) to the caller.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled exception on %s %s", scope.get("method"), scope.get("path"))
            if response_started:
                raise  # too late to send a clean 500; let the server close the connection
            await JSONResponse({"detail": "internal server error"}, status_code=500)(scope, receive, send)
