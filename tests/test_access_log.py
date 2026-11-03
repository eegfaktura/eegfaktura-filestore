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
import os
import uuid
from types import SimpleNamespace

import pytest

import app.health
from app.access_log import _request_id, _trace_ids
from app.config import settings
from app.logging_config import JsonFormatter
from tests.conftest import auth, make_token, new_tenant
from tests.test_delete_file import DELETE_FILE, stored_file
from tests.test_security import upload
from tests.test_upload_cleanup import add_file

# The contract of the access line, written out: widening the module's field lists must fail here.
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


def test_graphql_tenant_id_is_the_checked_stem_not_the_raw_argument(client, access_lines):
    tenant = new_tenant()
    _, headers = _personal_headers([tenant])
    r = _graphql(client, headers, "query Q($t: String!) { files(tenant: $t) { id } }",
                 {"t": f"{tenant}-max.muster@example.com"})
    assert r.status_code == 200 and "errors" not in r.json()
    (line,) = access_lines()
    assert line["tenant.id"] == tenant
    assert "max.muster" not in json.dumps(line).lower()


def test_rest_tenant_id_is_the_checked_stem_not_the_path_segment(client, access_lines):
    tenant = new_tenant()
    _, headers = _personal_headers([tenant])
    r = client.post(f"/filestore/upload/invoice/{tenant}-max.muster@example.com/{uuid.uuid4()}", headers=headers,
                    files={"file": ("a.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 400  # rejected after the tenant check
    (line,) = access_lines()
    assert line["tenant.id"] == tenant
    assert "max.muster" not in json.dumps(line).lower()


def test_gea_sub_tenant_and_its_stored_files_are_one_tenant(client, access_lines):
    stem = new_tenant()
    _, headers = _personal_headers([f"{stem}-003"])
    file_id = client.post(f"/filestore/upload/contract/{stem}-003/{uuid.uuid4()}", headers=headers,
                          files={"file": ("v.pdf", b"%PDF-1.4", "application/pdf")}).json()["id"]
    query = "query Q($t: String!, $id: UUID!) { a: files(tenant: $t) { id } b: file(id: $id) { id } }"
    r = _graphql(client, headers, query, {"t": f"{stem}-003", "id": file_id})
    assert r.status_code == 200 and "errors" not in r.json()
    lines = access_lines()
    assert [line["tenant.id"] for line in lines] == [stem, stem]


def test_superuser_tenant_is_logged_only_when_tenant_shaped(client, access_lines):
    _, headers = _personal_headers([new_tenant()], realm_access={"roles": ["superuser"]})
    query = "query Q($t: String!) { files(tenant: $t) { id } }"
    _graphql(client, headers, query, {"t": "rc100181-003"})
    _graphql(client, headers, query, {"t": "max.muster@example.com"})
    _graphql(client, headers, query, {"t": "gc123456-001"})
    first, second, gea = access_lines()
    assert first["tenant.id"] == "RC100181"
    assert "tenant.id" not in second and second["event.outcome"] == "success"
    assert gea["tenant.id"] == "GC123456"


def test_a_granted_tenant_outside_the_tenant_id_rule_is_left_out(client, access_lines):
    # the token grants the value, the check passes, but it is no tenant id the log may carry
    _, headers = _personal_headers(["max.muster"])
    r = client.post(f"/filestore/upload/invoice/max.muster/{uuid.uuid4()}", headers=headers,
                    files={"file": ("a.exe", b"MZ", "application/x-msdownload")})
    assert r.status_code == 400  # rejected after the passed tenant check
    (line,) = access_lines()
    assert "tenant.id" not in line and line["event.outcome"] == "failure"


@pytest.mark.parametrize("checked,logged", [("GC123456", "GC123456"), (" gc123456 ", "GC123456"),
                                            ("TE100200_X-1", "TE100200_X-1"), ("A" * 64, "A" * 64),
                                            ("A" * 65, None), ("-GC1", None), ("RC 1", None), ("", None)])
def test_the_tenant_id_rule(checked, logged):
    from app.logging_config import log_context, record_tenant_check

    token = log_context.set({})
    try:
        record_tenant_check(checked, True)
        assert log_context.get().get("tenant.id") == logged
    finally:
        log_context.reset(token)


def test_graphql_errors_are_logged_without_query_text_or_values(client):
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("strawberry.execution")
    logger.addHandler(handler)
    user_id = str(uuid.uuid4())
    try:
        _, headers = _personal_headers([new_tenant()])
        query = '{ invoices(tenant: "%s", userId: "%s") { id } }' % (new_tenant(), user_id)
        r = client.post("/graphql", headers=headers, json={"query": query})
        assert r.status_code == 200 and "Tenant not allowed" in r.text
    finally:
        logger.removeHandler(handler)
    raw = stream.getvalue()
    (line,) = [json.loads(x) for x in raw.splitlines()]
    assert line["log.level"] == "warn"
    assert line["error.type"] == "fastapi.exceptions.HTTPException"
    assert line["graphql.error.path"] == "invoices"
    assert user_id not in raw and "invoices(" not in raw and "Tenant not allowed" not in raw


# --- the request's fields on every line of the request, not only on the access line --------------

@pytest.fixture
def request_lines():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    old_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)

    def lines(logger):
        return [d for d in map(json.loads, stream.getvalue().splitlines()) if d["log.logger"] == logger]

    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(old_level)


def _uploaded(client):
    tenant = new_tenant()
    return tenant, upload(client, tenant, auth([tenant])).json()["id"]


def _with_request_id(tenants):
    return {**auth(tenants), "X-Request-Id": "req-lines"}


def test_rest_application_line_has_request_and_tenant(client, request_lines):
    tenant, file_id = _uploaded(client)
    os.remove(stored_file(file_id))

    assert client.get(f"/filestore/{file_id}", headers=_with_request_id([tenant])).status_code == 404

    (line,) = request_lines("app.rest.routers.filestore")
    assert line["log.level"] == "warn"
    assert line["request.id"] == "req-lines"
    assert line["tenant.id"] == tenant
    assert file_id in line["message"]  # the ids, not the on-disk path
    assert settings.FILESTORE_LOCAL_BASE_DIR not in line["message"]


def test_graphql_application_line_has_request_and_tenant(client, request_lines):
    tenant, file_id = _uploaded(client)
    os.remove(stored_file(file_id))

    r = client.post("/graphql", headers=_with_request_id([tenant]),
                    json={"query": DELETE_FILE, "variables": {"id": file_id}})
    assert r.json()["data"]["deleteFile"]["id"] == file_id

    (line,) = request_lines("app.graphql.resolvers.file_resolver")
    assert line["request.id"] == "req-lines"
    assert line["tenant.id"] == tenant


def test_graphql_error_line_after_a_passed_check_has_request_and_tenant(client, request_lines):
    tenant, _ = _uploaded(client)

    r = add_file(client, tenant, filename="x." + "p" * 600)
    assert r.json()["errors"][0]["path"] == ["addFile"]

    (line,) = request_lines("strawberry.execution")
    assert line["log.level"] == "error"
    assert len(line["request.id"]) == 32
    assert line["tenant.id"] == tenant


def test_a_line_before_any_passed_check_has_the_request_but_no_tenant(client, request_lines):
    r = client.get(f"/filestore/{uuid.uuid4()}", headers={"Authorization": "Bearer not-a-token",
                                                          "X-Request-Id": "req-lines"})
    assert r.status_code == 401

    (line,) = request_lines("app.auth")
    assert line["request.id"] == "req-lines"
    assert "tenant.id" not in line
    assert "segments" not in line["message"]  # the class name only, not PyJWT's "Not enough segments"


def test_the_line_of_an_unhandled_error_has_request_and_tenant(request_lines):
    import asyncio

    from app.access_log import AccessLogMiddleware
    from app.logging_config import record_tenant_check

    async def failing_app(scope, receive, send):
        record_tenant_check("RC100100", True)
        raise RuntimeError("boom")

    async def run():
        scope = {"type": "http", "method": "GET", "path": "/x", "headers": [(b"x-request-id", b"req-500")]}
        try:
            await AccessLogMiddleware(failing_app)(scope, None, None)
        except RuntimeError:
            # as uvicorn does after the middleware, in the request's task
            logging.getLogger("uvicorn.error").error("Exception in ASGI application")

    asyncio.run(run())
    (line,) = request_lines("uvicorn.error")
    assert line["request.id"] == "req-500"
    assert line["tenant.id"] == "RC100100"
