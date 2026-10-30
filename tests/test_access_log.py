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

# The access line through the real application: route template, status, tenant and client from the
# token check, request and trace ids — and nothing about the person (no user tracking).

import io
import json
import logging
import uuid
from types import SimpleNamespace

import pytest

import app.health
from app.access_log import _request_id, _trace_ids
from app.logging_config import JsonFormatter
from tests.conftest import make_token, new_tenant

ACCESS_FIELDS = {
    "@timestamp", "log.level", "log.logger", "service.name", "service.version", "message",
    "event.action", "event.outcome", "event.duration", "http.request.method", "http.route",
    "http.response.status_code", "request.id", "trace.id", "span.id", "tenant.id", "client.id",
    "graphql.operation.name",
}
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
SPAN_ID = "00f067aa0ba902b7"


@pytest.fixture
def access_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("app.access")
    old_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        yield lambda: [json.loads(line) for line in stream.getvalue().splitlines()]
    finally:
        logger.removeHandler(handler)
        logger.setLevel(old_level)


def _personal_headers(tenants, **claims):
    token = make_token(tenants, azp="eegfaktura-web", preferred_username="max.muster",
                       email="max@example.org", name="Max Muster", **claims)
    return token, {
        "Authorization": f"Bearer {token}",
        "User-Agent": "Mozilla/5.0 personal-agent",
        "X-Forwarded-For": "203.0.113.7",
        "X-Request-Id": "req-123",
        "traceparent": f"00-{TRACE_ID}-{SPAN_ID}-01",
    }


def _assert_nothing_personal(raw: str, token: str):
    for value in (token, "max.muster", "max@example.org", "Max Muster", "personal-agent", "203.0.113.7",
                  "testclient", "secret-query-value"):
        assert value not in raw


def test_rest_refusal_has_route_template_and_client_but_no_tenant(client, access_lines):
    tenant = new_tenant()
    token, headers = _personal_headers([new_tenant()])
    user_id = uuid.uuid4()
    r = client.post(f"/filestore/upload/invoice/{tenant}/{user_id}?x=secret-query-value",
                    headers=headers, files={"file": ("a.pdf", b"%PDF", "application/pdf")})
    assert r.status_code == 403
    assert r.headers["x-request-id"] == "req-123"

    (line,) = access_lines()
    assert set(line) <= ACCESS_FIELDS
    assert line["event.action"] == "http.access"
    assert line["event.outcome"] == "refused"
    assert line["http.request.method"] == "POST"
    assert line["http.route"] == "/filestore/upload/{file_category}/{tenant}/{user_id}"
    assert line["http.response.status_code"] == 403
    assert isinstance(line["event.duration"], int) and line["event.duration"] > 0
    assert line["request.id"] == "req-123"
    assert line["trace.id"] == TRACE_ID and line["span.id"] == SPAN_ID
    assert "tenant.id" not in line  # only after a passed check
    assert line["client.id"] == "eegfaktura-web"
    raw = json.dumps(line)
    assert str(user_id) not in raw
    _assert_nothing_personal(raw, token)


def test_graphql_access_line_has_the_operation_name(client, access_lines):
    tenant = new_tenant()
    token, headers = _personal_headers([tenant])
    r = client.post("/graphql", headers=headers, json={
        "query": "query ListFiles($tenant: String!) { files(tenant: $tenant) { id } }",
        "operationName": "ListFiles", "variables": {"tenant": tenant}})
    assert r.status_code == 200

    (line,) = access_lines()
    assert set(line) <= ACCESS_FIELDS
    assert line["http.route"] == "/graphql"
    assert line["graphql.operation.name"] == "ListFiles"
    assert line["tenant.id"] == tenant
    assert line["event.outcome"] == "success"
    _assert_nothing_personal(json.dumps(line), token)


def test_a_request_without_token_is_logged_as_refused_without_tenant(client, access_lines):
    r = client.get(f"/filestore/{uuid.uuid4()}")
    assert r.status_code in (401, 403)
    (line,) = access_lines()
    assert line["event.outcome"] == "refused"
    assert line["http.route"] == "/filestore/{file_id}"
    assert "tenant.id" not in line and "client.id" not in line
    assert len(line["request.id"]) == 32  # generated


def test_only_kube_probe_requests_are_kept_out_of_the_access_log(client, access_lines, monkeypatch):
    async def refused(**kwargs):
        raise ConnectionRefusedError()

    monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=refused))
    monkeypatch.setattr(app.health, "_last_result", None)
    client.get("/readyz", headers={"User-Agent": "kube-probe/1.31"})
    client.get("/healthz", headers={"User-Agent": "kube-probe/1.31"})
    monkeypatch.setattr(app.health, "_last_result", None)
    client.get("/readyz", headers={"User-Agent": "curl/8.0"})
    lines = access_lines()
    assert [(line["http.route"], line["http.response.status_code"]) for line in lines] == [("/readyz", 503)]


@pytest.mark.parametrize("value,kept", [
    (b"abc-123_X.y:z", True), (b"", False), (b"has space", False), (b"x" * 129, False), (b"a\nb", False),
])
def test_a_caller_request_id_is_kept_only_when_it_is_a_plain_token(value, kept):
    assert (_request_id(value) == value.decode()) is kept


@pytest.mark.parametrize("value,ok", [
    (f"00-{TRACE_ID}-{SPAN_ID}-01", True),
    (f"01-{TRACE_ID}-{SPAN_ID}-01-future", True),
    (f"00-{TRACE_ID}-{SPAN_ID}-01-extra", False),
    (f"ff-{TRACE_ID}-{SPAN_ID}-01", False),
    (f"00-{'0' * 32}-{SPAN_ID}-01", False),
    (f"00-{TRACE_ID.upper()}-{SPAN_ID}-01", False),
    ("garbage", False),
])
def test_traceparent(value, ok):
    assert bool(_trace_ids(value.encode())) is ok


def test_rest_tenant_is_logged_upper_case_after_a_passed_check(client, access_lines):
    tenant = new_tenant()
    _, headers = _personal_headers([tenant])
    r = client.post(f"/filestore/upload/invoice/{tenant.lower()}/{uuid.uuid4()}", headers=headers,
                    files={"file": ("a.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 400  # rejected after the tenant check
    (line,) = access_lines()
    assert line["tenant.id"] == tenant
    assert line["event.outcome"] == "failure"


def _graphql(client, headers, query, variables):
    return client.post("/graphql", headers=headers, json={"query": query, "variables": variables})


def test_graphql_tenant_refusal_is_logged_as_refused(client, access_lines):
    _, headers = _personal_headers([new_tenant()])
    r = _graphql(client, headers, "query Q($t: String!) { files(tenant: $t) { id } }", {"t": new_tenant()})
    assert r.status_code == 200 and "Tenant not allowed" in r.text
    (line,) = access_lines()
    assert line["event.outcome"] == "refused"
    assert "tenant.id" not in line


def test_graphql_mixed_tenant_checks_are_refused_without_tenant(client, access_lines):
    own = new_tenant()
    _, headers = _personal_headers([own])
    query = "query Q($a: String!, $b: String!) { x: files(tenant: $b) { id } y: files(tenant: $a) { id } }"
    r = _graphql(client, headers, query, {"a": own, "b": new_tenant()})
    assert r.status_code == 200 and "Tenant not allowed" in r.text
    (line,) = access_lines()
    assert line["event.outcome"] == "refused"
    assert "tenant.id" not in line


def test_the_context_survives_an_unhandled_error_for_the_traceback_line():
    import asyncio

    from app.access_log import AccessLogMiddleware
    from app.logging_config import log_context

    async def failing_app(scope, receive, send):
        raise RuntimeError("boom")

    async def run():
        scope = {"type": "http", "method": "GET", "path": "/x", "headers": [(b"x-request-id", b"req-500")]}
        try:
            await AccessLogMiddleware(failing_app)(scope, None, None)
        except RuntimeError:
            return (log_context.get() or {}).get("request.id")

    assert asyncio.run(run()) == "req-500"
