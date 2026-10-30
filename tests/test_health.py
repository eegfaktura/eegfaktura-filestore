# Kubernetes probe endpoints: unauthenticated, plain "ok" / "unavailable", /readyz checks the
# database, the probe paths are kept out of the access log.

import asyncio
import logging

from sqlalchemy.ext.asyncio import create_async_engine

import app.health
from app.db import session as db_session


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


def test_readyz_is_503_when_the_database_is_unreachable(client, monkeypatch, caplog):
    # Port 1 on localhost: nothing listens, the connection is refused.
    broken = create_async_engine("postgresql+asyncpg://nobody:secret@127.0.0.1:1/nothing")
    monkeypatch.setattr(db_session, "engine", broken)
    with caplog.at_level(logging.WARNING, logger="app.health"):
        r = client.get("/readyz")
    assert r.status_code == 503
    assert r.text == "unavailable"
    assert "readiness check failed" in caplog.text


def test_readyz_is_503_when_the_database_does_not_answer_in_time(client, monkeypatch):
    async def hanging():
        await asyncio.sleep(10)

    monkeypatch.setattr(app.health, "_ping_db", hanging)
    monkeypatch.setattr(app.health, "READY_TIMEOUT_SECONDS", 0.1)
    r = client.get("/readyz")
    assert r.status_code == 503
    assert r.text == "unavailable"


def test_the_probe_paths_are_not_access_logged():
    f = app.health.ProbeAccessLogFilter()

    def record(path):
        return logging.LogRecord("uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
                                 ("10.0.0.1:1234", "GET", path, "1.1", 200), None)

    assert not f.filter(record("/healthz"))
    assert not f.filter(record("/readyz"))
    assert not f.filter(record("/readyz?x=1"))
    assert f.filter(record("/filestore/upload/contract/RC100000/1"))
    assert f.filter(record("/graphql"))
