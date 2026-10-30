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

# Kubernetes probe endpoints: unauthenticated, plain "ok" / "unavailable", /readyz pings the
# database on a connection of its own (one ping at a time), only kube-probe requests are kept out
# of the access log.

import asyncio
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

import app.health


@pytest.fixture(autouse=True)
def fresh_readiness_state(monkeypatch):
    # No result of an earlier test may be reused (results younger than 1 s are shared).
    monkeypatch.setattr(app.health, "_last_result", None)
    monkeypatch.setattr(app.health, "_running", None)
    monkeypatch.setattr(app.health, "_last_saturation_warning", None)


def test_healthz_without_token_is_200_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.text == "ok"
    assert r.headers["content-type"].startswith("text/plain")


def test_readyz_without_token_is_200_ok_with_the_database_up(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.text == "ok"
    assert r.headers["content-type"].startswith("text/plain")


def test_readyz_is_503_when_the_database_refuses_the_connection(client, monkeypatch, caplog):
    seen = {}

    async def refused(**kwargs):
        seen.update(kwargs)
        raise ConnectionRefusedError("connection refused")

    monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=refused))
    with caplog.at_level(logging.WARNING, logger="app.health"):
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.text == "unavailable"
    assert "readiness check failed" in caplog.text
    assert "ConnectionRefusedError" in caplog.text
    # Same connect arguments as the application engine (host, port, user, database, URL query).
    assert seen["host"] == app.health.db_session.engine.url.host
    assert seen["database"] == app.health.db_session.engine.url.database
    # The driver's own timeouts bound the ping (no cancel from outside).
    assert 0 < seen["timeout"] <= 2
    assert 0 < seen["command_timeout"] <= 2


def test_readyz_stays_200_when_postgres_has_no_free_connection(client, monkeypatch, caplog):
    # SQLSTATE 53300 (too_many_connections) on the ping's own connection: the application pool still
    # holds its connections, so the service stays ready; the warning is rate-limited.
    import asyncpg

    async def saturated(**kwargs):
        raise asyncpg.TooManyConnectionsError("sorry, too many clients already")

    monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=saturated))
    with caplog.at_level(logging.WARNING, logger="app.health"):
        for _ in range(2):
            monkeypatch.setattr(app.health, "_last_result", None)
            r = client.get("/readyz")
            assert r.status_code == 200
            assert r.text == "ok"
    assert caplog.text.count("too_many_connections") == 1


def test_the_ping_passes_url_query_parameters_like_the_application(monkeypatch):
    seen = {}

    async def connect(**kwargs):
        seen.update(kwargs)
        raise ConnectionRefusedError()

    engine = create_async_engine("postgresql+asyncpg://u:p@db.example:6543/d?ssl=require")
    try:
        monkeypatch.setattr(app.health.db_session, "engine", engine)
        monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=connect))
        assert asyncio.run(app.health._ready()) is False
    finally:
        asyncio.run(engine.dispose())
    assert seen["host"] == "db.example"
    assert seen["port"] == 6543
    assert seen["ssl"] == "require"
    assert seen["timeout"] == seen["command_timeout"] == app.health.READY_TIMEOUT_SECONDS


def test_a_timeout_is_logged_with_its_type(client, monkeypatch, caplog):
    async def times_out(**kwargs):
        raise TimeoutError()

    monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=times_out))
    with caplog.at_level(logging.WARNING, logger="app.health"):
        assert client.get("/readyz").status_code == 503
    assert "TimeoutError" in caplog.text


def test_concurrent_readiness_checks_share_one_ping(monkeypatch):
    pings = 0

    async def slow_ping():
        nonlocal pings
        pings += 1
        await asyncio.sleep(0.05)

    monkeypatch.setattr(app.health, "_ping_db", slow_ping)

    async def run():
        results = await asyncio.gather(*(app.health._ready() for _ in range(5)))
        again = await app.health._ready()  # result younger than 1 s: reused
        return results, again

    results, again = asyncio.run(run())
    assert results == [True] * 5
    assert again is True
    assert pings == 1


def _marked(path, root_path="", user_agent=b"kube-probe/1.31"):
    scope = {"type": "http", "path": path, "root_path": root_path,
             "headers": [(b"user-agent", user_agent)]}
    return app.health.is_kube_probe(scope)


def test_only_the_exact_probe_paths_are_marked():
    assert _marked("/healthz")
    assert _marked("/readyz")
    assert _marked("/api/readyz", root_path="/api")
    assert not _marked("/filestore/readyz")
    assert not _marked("/readyz/x")


def test_only_kube_probe_user_agents_are_marked():
    assert not _marked("/readyz", user_agent=b"curl/8.0")
    assert not _marked("/readyz", user_agent=b"Mozilla/5.0 kube-probe/1.31")
