# vfeeg-filestor File handling for eegFaktura
# Copyright (C) 2026  Matthias Martetschläger
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#

# Kubernetes probes. Both endpoints are unauthenticated (the documented exception to "every
# endpoint requires a bearer token") and answer only "ok" / "unavailable" — no error text, versions
# or hosts in the body; the reason a readiness check fails goes to the log.

import asyncio
import contextvars
import logging
import time
from typing import Optional

import asyncpg
from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from app.db import session as db_session

logger = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 2.0
RESULT_MAX_AGE_SECONDS = 1.0
PROBE_PATHS = ("/healthz", "/readyz")

router = APIRouter()


@router.get("/healthz", response_class=PlainTextResponse, include_in_schema=False)
async def healthz() -> str:
    # Liveness: no dependency checks, so a database outage never causes a restart loop.
    return "ok"


async def _ping_db() -> None:
    # A connection of its own, not from the application pool: a busy pool must not make a healthy
    # service NotReady, and anonymous /readyz calls must not tie up pooled connections. The
    # driver's own connect and statement timeouts bound it; nothing cancels it from outside.
    # The connect arguments come from the application engine's dialect, so URL query parameters
    # (e.g. ssl) reach the ping like the application; the two keys SQLAlchemy's adapter consumes
    # itself are not asyncpg.connect arguments.
    engine = db_session.engine
    cargs, cparams = engine.dialect.create_connect_args(engine.url)
    cparams.pop("prepared_statement_cache_size", None)
    cparams.pop("prepared_statement_name_func", None)
    conn = await asyncpg.connect(
        *cargs, **cparams, timeout=READY_TIMEOUT_SECONDS, command_timeout=READY_TIMEOUT_SECONDS,
    )
    try:
        await conn.fetchval("SELECT 1")
    finally:
        await conn.close(timeout=READY_TIMEOUT_SECONDS)


_last_result: Optional[tuple[float, bool]] = None  # (monotonic time, ready)
_running: Optional[asyncio.Task] = None


TOO_MANY_CONNECTIONS = "53300"
SATURATION_WARN_INTERVAL_SECONDS = 60.0
_last_saturation_warning: Optional[float] = None


async def _check() -> bool:
    global _last_result, _last_saturation_warning
    try:
        await _ping_db()
        ready = True
    except Exception as e:
        if getattr(e, "sqlstate", None) == TOO_MANY_CONNECTIONS:
            # Postgres has no free connection for the ping, but the application's pool still holds
            # its own: stay ready, so a saturated shared Postgres does not become a full outage.
            now = time.monotonic()
            if _last_saturation_warning is None or now - _last_saturation_warning >= SATURATION_WARN_INTERVAL_SECONDS:
                _last_saturation_warning = now
                logger.warning("readiness check: database has no free connection (too_many_connections); "
                               "staying ready, the application pool can still serve")
            ready = True
        else:
            logger.warning("readiness check failed: database not reachable: %r", e)
            ready = False
    _last_result = (time.monotonic(), ready)
    return ready


async def _ready() -> bool:
    # One ping at a time per process: concurrent callers share the running ping, and a result
    # younger than RESULT_MAX_AGE_SECONDS is reused, so public callers cannot multiply the DB load.
    global _running
    if _last_result is not None and time.monotonic() - _last_result[0] < RESULT_MAX_AGE_SECONDS:
        return _last_result[1]
    if _running is None or _running.done():
        _running = asyncio.create_task(_check())
    # shield: a caller that goes away does not cancel the ping the others wait for.
    return await asyncio.shield(_running)


@router.get("/readyz", response_class=PlainTextResponse, include_in_schema=False)
async def readyz() -> PlainTextResponse:
    if await _ready():
        return PlainTextResponse("ok")
    return PlainTextResponse("unavailable", status_code=503)


# --- access log ------------------------------------------------------------------------------------
# uvicorn writes the access line from inside the application's send(), so a context variable set
# by the middleware below is visible to the log filter. Only Kubernetes' own probe requests are
# left out; any other caller of the probe paths stays in the log.

_kube_probe_request: contextvars.ContextVar[bool] = contextvars.ContextVar("kube_probe_request", default=False)


class ProbeAccessLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        path = scope.get("path", "")
        root_path = scope.get("root_path", "")
        if root_path and path.startswith(root_path):
            path = path[len(root_path):]
        if scope["type"] == "http" and path in PROBE_PATHS:
            user_agent = dict(scope.get("headers") or []).get(b"user-agent", b"")
            if user_agent.startswith(b"kube-probe/"):
                _kube_probe_request.set(True)
        await self.app(scope, receive, send)


class ProbeAccessLogFilter(logging.Filter):
    """Drops uvicorn access log lines of Kubernetes probe requests (one per probe period would flood the log)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not _kube_probe_request.get()


# Installed once per process (this module is imported once), not per create_app().
logging.getLogger("uvicorn.access").addFilter(ProbeAccessLogFilter())
