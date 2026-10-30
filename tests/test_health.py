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

import app.health


@pytest.fixture(autouse=True)
def fresh_readiness_state(monkeypatch):
    # No result of an earlier test may be reused (results younger than 1 s are shared).
    monkeypatch.setattr(app.health, "_last_result", None)
    monkeypatch.setattr(app.health, "_running", None)


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
    # The driver's own timeouts bound the ping (no cancel from outside).
    assert 0 < seen["timeout"] <= 2
    assert 0 < seen["command_timeout"] <= 2


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


def test_only_kube_probe_requests_are_kept_out_of_the_access_log(client, monkeypatch):
    # TestClient does not write uvicorn's access log. The fake connect runs inside the request, as
    # uvicorn's send() does, and records what the access-log filter decides there.
    decisions = []
    record = logging.LogRecord("uvicorn.access", logging.INFO, "", 0, "", None, None)

    async def connect(**kwargs):
        decisions.append(app.health.ProbeAccessLogFilter().filter(record))
        raise ConnectionRefusedError()

    monkeypatch.setattr(app.health, "asyncpg", SimpleNamespace(connect=connect))
    client.get("/readyz", headers={"User-Agent": "kube-probe/1.31"})
    monkeypatch.setattr(app.health, "_last_result", None)
    client.get("/readyz", headers={"User-Agent": "curl/8.0"})
    assert decisions == [False, True]
