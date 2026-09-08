from __future__ import annotations

import hmac
import logging

from fastapi import Depends, Header, HTTPException, status

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)
_warned_unconfigured = False


async def require_api_key(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    settings: Settings = Depends(get_settings),
) -> None:
    """Gate every route (except /health) behind a shared-secret API key.

    debug=False (production posture): api_key must be set -- see the startup
    check in create_app(), which refuses to boot without one -- so reaching
    here with settings.api_key unset can't happen outside debug mode.

    debug=True (local/demo default): api_key is optional so the app keeps
    working unauthenticated out of the box, matching today's zero-config
    behavior, but this is loudly logged once so it's never a silent gap.
    """
    if not settings.api_key:
        global _warned_unconfigured
        if not _warned_unconfigured:
            logger.warning(
                "API_KEY is not set -- every endpoint is running WITHOUT authentication. "
                "Set API_KEY (and DEBUG=false for any non-local deployment) to require it."
            )
            _warned_unconfigured = True
        return

    if not x_api_key or not hmac.compare_digest(x_api_key, settings.api_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing or invalid API key")
