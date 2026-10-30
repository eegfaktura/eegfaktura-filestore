# vfeeg-filestor File handling for eegFaktura
# Copyright (C) 2023  Matthias Poettinger
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
import logging

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from sqlalchemy import text

from app.db import session as db_session

logger = logging.getLogger(__name__)

READY_TIMEOUT_SECONDS = 2.0
PROBE_PATHS = ("/healthz", "/readyz")

router = APIRouter()


@router.get("/healthz", response_class=PlainTextResponse, include_in_schema=False)
async def healthz() -> str:
    # Liveness: no dependency checks, so a database outage never causes a restart loop.
    return "ok"


async def _ping_db() -> None:
    async with db_session.engine.connect() as conn:
        await conn.execute(text("SELECT 1"))


@router.get("/readyz", response_class=PlainTextResponse, include_in_schema=False)
async def readyz() -> PlainTextResponse:
    try:
        await asyncio.wait_for(_ping_db(), timeout=READY_TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning("readiness check failed: database not reachable: %s: %s", type(e).__name__, e)
        return PlainTextResponse("unavailable", status_code=503)
    return PlainTextResponse("ok")


class ProbeAccessLogFilter(logging.Filter):
    """Drops uvicorn access log lines for the probe paths (one per probe period would flood the log)."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        # uvicorn.access: (client_addr, method, full_path, http_version, status_code)
        if isinstance(args, tuple) and len(args) >= 3 and isinstance(args[2], str):
            return args[2].split("?", 1)[0] not in PROBE_PATHS
        return True
