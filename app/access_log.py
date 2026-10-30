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

# One access line per HTTP request (event.action=http.access), written when the response is done,
# so it carries the tenant and client the token check put into the request's log context
# (app.auth). Route template only — no raw path, no query, no client address, no user agent, no
# user (no user tracking). Kubernetes' own probe requests are left out (app.health.is_kube_probe).

import logging
import re
import time
import uuid
from typing import Optional

from strawberry.extensions import SchemaExtension

from app.health import is_kube_probe
from app.logging_config import log_context

logger = logging.getLogger("app.access")

_REQUEST_ID = re.compile(r"[A-Za-z0-9._:-]{1,128}")
_TRACEPARENT = re.compile(r"([0-9a-f]{2})-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}(-.*)?")
_GRAPHQL_NAME = re.compile(r"[_A-Za-z][_0-9A-Za-z]{0,63}")


def _request_id(value: Optional[bytes]) -> str:
    # A caller's X-Request-Id is kept only when it is a plain token; anything else gets a new id.
    text = (value or b"").decode("latin-1")
    return text if _REQUEST_ID.fullmatch(text) else uuid.uuid4().hex


def _trace_ids(value: Optional[bytes]) -> dict:
    # W3C traceparent: version-traceid-parentid-flags; version ff and all-zero ids are invalid.
    m = _TRACEPARENT.fullmatch((value or b"").decode("latin-1").strip())
    if not m or m.group(1) == "ff" or (m.group(1) == "00" and m.group(4)):
        return {}
    if set(m.group(2)) == {"0"} or set(m.group(3)) == {"0"}:
        return {}
    return {"trace.id": m.group(2), "span.id": m.group(3)}


def _route_template(scope) -> Optional[str]:
    # FastAPI keeps the included router's own route in scope["route"] (path without the router's
    # prefix) and the full template in its effective route context; tests pin the full form.
    effective = (scope.get("fastapi") or {}).get("effective_route_context")
    return getattr(effective, "path_format", None) or getattr(scope.get("route"), "path", None)


def _outcome(status: int) -> str:
    if status in (401, 403):
        return "refused"
    return "failure" if status >= 400 else "success"


class AccessLogMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        ctx = {"request.id": _request_id(headers.get(b"x-request-id"))}
        ctx.update(_trace_ids(headers.get(b"traceparent")))
        # request.state is backed by scope["state"]: the token check adds tenant.id and client.id here.
        scope.setdefault("state", {})["log_context"] = ctx
        token = log_context.set(ctx)
        status = 500  # stays when the application fails before it answers
        start = time.perf_counter_ns()

        async def send_with_status(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                message["headers"] = [*message.get("headers", []),
                                      (b"x-request-id", ctx["request.id"].encode("latin-1"))]
            await send(message)

        try:
            await self.app(scope, receive, send_with_status)
        finally:
            if not is_kube_probe(scope):
                route = _route_template(scope)
                logger.info("%s %s %s", scope["method"], route or "-", status, extra={
                    "event.action": "http.access",
                    "event.outcome": _outcome(status),
                    "event.duration": time.perf_counter_ns() - start,
                    "http.request.method": scope["method"],
                    "http.route": route,
                    "http.response.status_code": status,
                })
            log_context.reset(token)


class GraphQLOperationName(SchemaExtension):
    """Puts the GraphQL operation name into the request's log context (every call is one path)."""

    def on_execute(self):
        name = self.execution_context.operation_name
        ctx = log_context.get()
        if ctx is not None and name and _GRAPHQL_NAME.fullmatch(name):
            ctx["graphql.operation.name"] = name
        yield
