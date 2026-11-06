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

# The logging module: level and format parsing, the JSON and text line, the field whitelist, and
# the applied setup (in this process, the logging state restored afterwards; one start of main.py
# in a subprocess).

import json
import logging
import os
import re
import subprocess
import sys
import uuid
import warnings

import alembic.command
import alembic.config
import pytest
import sqlalchemy
from sqlalchemy.exc import DBAPIError

from app import logging_config
from app.db import session as db_session
from app.config import Settings
from app.logging_config import (JsonFormatter, TextFormatter, configure_logging, dict_config, log_context,
                                log_service_start, parse_format, parse_level)
from tests.conftest import auth, new_tenant

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _record(level=logging.INFO, msg="hello %s", args=("world",), exc_info=None, **extra):
    record = logging.LogRecord("app.test", level, __file__, 1, msg, args, exc_info)
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize("value,level", [
    ("trace", logging_config.TRACE), ("debug", logging.DEBUG), ("INFO", logging.INFO),
    ("warn", logging.WARNING), ("warning", logging.WARNING), (" error ", logging.ERROR),
    ("", logging.INFO), ("  ", logging.INFO),  # set but empty: the default
])
def test_known_levels_are_accepted(value, level):
    assert parse_level(value) == level


@pytest.mark.parametrize("value", ["verbose", "critical", "5"])
def test_an_unknown_level_is_refused(value):
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        parse_level(value)


def test_formats():
    assert parse_format("JSON") == "json"
    assert parse_format("text") == "text"
    assert parse_format("") == "text"
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        parse_format("ecs")


def test_json_line_has_the_common_fields():
    line = JsonFormatter(service_version="1.2.3").format(_record(level=logging.WARNING))
    assert "\n" not in line
    doc = json.loads(line)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", doc["@timestamp"])
    assert doc["log.level"] == "warn"
    assert doc["log.logger"] == "app.test"
    assert doc["service.name"] == "eegfaktura-filestore"
    assert doc["service.version"] == "1.2.3"
    assert doc["message"] == "hello world"


def test_trace_and_critical_map_to_the_five_levels():
    assert json.loads(JsonFormatter().format(_record(level=logging_config.TRACE)))["log.level"] == "trace"
    assert json.loads(JsonFormatter().format(_record(level=logging.CRITICAL)))["log.level"] == "error"


def test_request_context_and_allowed_extra_fields_are_written():
    token = log_context.set({"request.id": "r1", "tenant.id": "RC100100", "client.id": "at.ourproject.vfeeg.app"})
    try:
        doc = json.loads(JsonFormatter().format(_record(**{"event.action": "file.delete.failed"})))
    finally:
        log_context.reset(token)
    assert doc["request.id"] == "r1"
    assert doc["tenant.id"] == "RC100100"
    assert doc["client.id"] == "at.ourproject.vfeeg.app"
    assert doc["event.action"] == "file.delete.failed"


def test_fields_outside_the_whitelist_are_never_written():
    record = _record(**{"user.email": "max@example.org", "password": "secret", "user_agent": "curl/8",
                        "client.ip": "10.1.2.3", "preferred_username": "max"})
    out = JsonFormatter().format(record) + TextFormatter().format(record)
    for value in ("max@example.org", "secret", "curl/8", "10.1.2.3", "max\""):
        assert value not in out


def test_an_exception_becomes_the_error_fields():
    try:
        raise KeyError("missing")
    except KeyError:
        record = _record(level=logging.ERROR, exc_info=sys.exc_info())
    doc = json.loads(JsonFormatter().format(record))
    assert doc["error.type"] == "builtins.KeyError"
    assert doc["error.message"] == "'missing'"
    assert "Traceback" in doc["error.stack_trace"]


def test_text_line_quotes_values_with_spaces():
    token = log_context.set({"request.id": "r1", "tenant.id": "RC 1"})
    try:
        line = TextFormatter().format(_record())
    finally:
        log_context.reset(token)
    assert re.match(r"\d{4}-.*Z info  app.test: hello world request.id=r1 tenant.id=\"RC 1\"$", line)


OWN_ENV = ("LOG_LEVEL", "APP_LOG_LEVEL", "LOG_FORMAT", "SERVICE_VERSION", "DEPLOYMENT_ENVIRONMENT")


@pytest.fixture
def setup_from_env(monkeypatch, capsys):
    """Applies the logging setup in this process from the given environment (read by Settings as at
    start) and returns the settings; the lines go to the captured stdout. Afterwards the loggers the
    setup touches, the warnings capture and sys.excepthook are as before."""
    loggers = [logging.getLogger(), *map(logging.getLogger, dict_config(logging.INFO, "text", "")["loggers"])]
    saved = [(lg, lg.level, lg.handlers[:], lg.propagate, lg.disabled) for lg in loggers]
    hook = sys.excepthook

    def apply(**env):
        for name in OWN_ENV:
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        settings = Settings()
        configure_logging(settings)
        capsys.readouterr()
        return settings

    yield apply
    logging.captureWarnings(False)
    sys.excepthook = hook
    for lg, level, handlers, propagate, disabled in saved:
        for handler in lg.handlers:
            if handler not in handlers:
                handler.close()
        lg.handlers[:] = handlers
        lg.setLevel(level)
        lg.propagate, lg.disabled = propagate, disabled


def _lines(capsys):
    return capsys.readouterr().out.splitlines()


def _write_sample_lines():
    logging.getLogger("uvicorn.error").info("started")
    logging.getLogger("uvicorn.access").info("127.0.0.1 GET /x?q=1")
    logging.getLogger("app.x").debug("dbg")
    logging.getLogger("app.x").info("app line")


def test_the_applied_setup_writes_one_json_object_per_line_and_drops_uvicorns_access_line(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json", LOG_LEVEL="info", SERVICE_VERSION="9.9.9")
    _write_sample_lines()
    out = capsys.readouterr()
    docs = [json.loads(line) for line in out.out.splitlines()]
    assert [(d["log.logger"], d["message"]) for d in docs] == [("uvicorn.error", "started"), ("app.x", "app line")]
    assert {d["service.version"] for d in docs} == {"9.9.9"}
    assert out.err == ""


def test_app_log_level_is_still_read_when_log_level_is_not_set(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json", APP_LOG_LEVEL="debug")
    _write_sample_lines()
    assert "dbg" in [json.loads(line)["message"] for line in _lines(capsys)]


def test_log_level_wins_over_app_log_level(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "warn")
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    assert Settings().LOG_LEVEL == "warn"


def test_an_unknown_log_level_stops_the_start(setup_from_env):
    with pytest.raises(ValueError, match="LOG_LEVEL='verbose'"):
        setup_from_env(LOG_LEVEL="verbose")


def test_text_line_escapes_control_characters():
    msg = 'forged' + chr(10) + '2026-01-01T00:00:00.000Z error x: injected' + chr(27) + '[31m'
    line = TextFormatter().format(_record(msg=msg, args=None))
    assert chr(10) not in line and chr(27) not in line
    assert 'forged' + chr(92) + 'n2026' in line and chr(92) + 'x1b[31m' in line


def test_uvicorn_connection_lines_stay_out_even_at_trace(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json", LOG_LEVEL="trace")
    logging.getLogger("uvicorn.error").log(5, "%s - HTTP connection made", "203.0.113.7:51234")
    logging.getLogger("uvicorn.error").debug("uvicorn debug")
    logging.getLogger("app.x").log(5, "app trace")
    lines = _lines(capsys)
    assert [json.loads(line)["message"] for line in lines] == ["uvicorn debug", "app trace"]
    assert "203.0.113.7" not in "".join(lines)


def test_empty_log_level_and_format_mean_the_defaults(setup_from_env, capsys):
    settings = setup_from_env(LOG_LEVEL="", LOG_FORMAT="")
    assert (settings.LOG_LEVEL, settings.LOG_FORMAT) == ("info", "text")
    _write_sample_lines()
    lines = _lines(capsys)
    assert len(lines) == 2 and not lines[0].startswith("{")  # text, info: no debug line
    assert not any("dbg" in line for line in lines)


def test_warnings_go_through_the_logging_setup(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json")
    with warnings.catch_warnings():
        warnings.simplefilter("always")
        warnings.warn("careful", stacklevel=1)
    out = capsys.readouterr()
    docs = [json.loads(line) for line in out.out.splitlines()]
    assert docs[-1]["log.logger"] == "py.warnings" and "careful" in docs[-1]["message"]
    assert out.err == ""


def test_an_empty_log_level_falls_back_to_app_log_level(monkeypatch):
    for name in OWN_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LOG_LEVEL", "")
    monkeypatch.setenv("APP_LOG_LEVEL", "debug")
    monkeypatch.setenv("LOG_FORMAT", "")
    settings = Settings()
    assert (settings.LOG_LEVEL, settings.LOG_FORMAT) == ("debug", "text")


# A file name too long for files.name fails on the row with the user id, a too long extension on the
# attribute row with the file name; both reach the server's error line as an unhandled DBAPIError.
@pytest.mark.parametrize("filename", ["max-muster" + "n" * 130 + ".pdf", "max-muster." + "p" * 600],
                         ids=["file-row", "attribute-row"])
def test_an_unhandled_db_error_on_upload_logs_no_sql_parameters(client, filename):
    tenant = new_tenant()
    user_id = uuid.uuid4()
    with pytest.raises(DBAPIError) as failed:
        client.post(f"/filestore/upload/contract/{tenant}/{user_id}", headers=auth([tenant]),
                    files={"file": (filename, b"%PDF-1.4", "application/pdf")})

    doc = json.loads(JsonFormatter().format(
        _record(level=logging.ERROR, exc_info=(failed.type, failed.value, failed.tb))))
    assert doc["error.type"] == f"sqlalchemy.exc.{failed.type.__qualname__}"
    # the reason stays: string_data_right_truncation, in the server's words (they depend on its lc_messages)
    assert failed.value.orig.sqlstate == "22001"
    assert str(failed.value.orig) in doc["error.message"]
    for field in ("error.message", "error.stack_trace"):
        for value in (str(user_id), user_id.hex, "max-muster", tenant):
            assert value not in doc[field]


def test_every_engine_hides_sql_parameters(setup_from_env, monkeypatch):
    # setup_from_env: alembic/env.py applies the logging setup, the fixture restores it afterwards
    assert db_session.engine.sync_engine.hide_parameters is True
    engines = []

    def capture(*args, **kwargs):
        engines.append(real(*args, **kwargs))
        return engines[-1]

    real = sqlalchemy.engine_from_config
    monkeypatch.setattr(sqlalchemy, "engine_from_config", capture)
    cfg = alembic.config.Config(os.path.join(REPO, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(REPO, "alembic"))
    alembic.command.current(cfg)
    assert [engine.hide_parameters for engine in engines] == [True]


@pytest.mark.parametrize("level,effective", [("info", "info"), ("warning", "warn"), ("error", "error")])
def test_one_start_up_line_with_version_and_effective_level(setup_from_env, capsys, level, effective):
    setup_from_env(LOG_FORMAT="json", LOG_LEVEL=level, SERVICE_VERSION="9.9.9")
    log_service_start()
    starts = [d for d in map(json.loads, _lines(capsys)) if d.get("event.action") == "service.start"]
    assert len(starts) == 1
    assert starts[0]["log.level"] == "info"
    assert starts[0]["log.logger"] == "app.start"
    assert starts[0]["service.version"] == "9.9.9"
    assert starts[0]["log.effective_level"] == effective
    assert starts[0]["message"] == "service start"  # the common start message of all services


@pytest.mark.parametrize("level", ["warn", "error"])
def test_the_access_line_is_written_at_info_whatever_the_level(setup_from_env, capsys, level):
    setup_from_env(LOG_FORMAT="json", LOG_LEVEL=level)
    logging.getLogger("app.access").info("GET /healthz 200")
    logging.getLogger("app.x").info("app line")
    assert [json.loads(line)["log.logger"] for line in _lines(capsys)] == ["app.access"]


def test_an_uncaught_exception_is_one_json_line(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json")
    try:
        raise OSError("key file unreadable")
    except OSError:
        sys.excepthook(*sys.exc_info())
    out = capsys.readouterr()
    (doc,) = [json.loads(line) for line in out.out.splitlines()]
    assert doc["log.logger"] == "app.uncaught"
    assert doc["log.level"] == "error"  # critical, written as the highest of the five levels
    assert doc["error.type"] == "builtins.OSError"
    assert doc["error.message"] == "key file unreadable"
    assert "Traceback" in doc["error.stack_trace"]
    assert out.err == ""


def test_a_keyboard_interrupt_goes_to_the_default_hook(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json")
    try:
        raise KeyboardInterrupt()
    except KeyboardInterrupt:
        sys.excepthook(*sys.exc_info())
    out = capsys.readouterr()
    assert out.out == ""
    assert "KeyboardInterrupt" in out.err


def _run(args, **env):
    full_env = {k: v for k, v in os.environ.items() if k not in OWN_ENV}
    full_env.update(env)
    return subprocess.run(args, cwd=REPO, env=full_env, capture_output=True, text=True, timeout=60)


# port 1: nothing listens there, the connection is refused at once
_DB_DOWN = {"LOG_FORMAT": "json", "DB_HOSTNAME": "127.0.0.1", "DB_PORT": "1"}


def _assert_json_failure(r):
    assert r.returncode != 0
    docs = [json.loads(line) for line in r.stdout.splitlines()]
    assert docs[-1]["log.logger"] == "app.uncaught"
    assert docs[-1]["error.type"] == "sqlalchemy.exc.OperationalError"
    assert "Traceback" not in r.stderr


def test_alembic_against_a_database_that_is_down_fails_with_a_json_line():
    _assert_json_failure(_run([sys.executable, "-m", "alembic", "upgrade", "head"], **_DB_DOWN))


@pytest.mark.skipif(os.name == "nt", reason="entrypoint.sh is the start script of the Linux image")
def test_the_entrypoint_stops_when_the_migration_fails():
    # python3 and alembic of this interpreter first in PATH, as in the image's venv
    path = os.path.dirname(sys.executable) + os.pathsep + os.environ.get("PATH", "")
    r = _run(["bash", "entrypoint.sh"], PATH=path, **_DB_DOWN)
    _assert_json_failure(r)
    assert "service.start" not in r.stdout


_START = ("import runpy, uvicorn; uvicorn.run = lambda *args, **kwargs: None; "
          "runpy.run_path('main.py', run_name='__main__')")


def test_main_starts_with_one_json_start_up_line_and_no_secret():
    r = _run([sys.executable, "-c", _START], LOG_FORMAT="json",LOG_LEVEL="warning", SERVICE_VERSION="9.9.9", DB_PASSWORD="db-secret-value")
    assert r.returncode == 0, r.stderr
    starts = [d for d in map(json.loads, r.stdout.splitlines()) if d.get("event.action") == "service.start"]
    assert len(starts) == 1
    assert starts[0]["log.level"] == "info"
    assert starts[0]["service.version"] == "9.9.9"
    assert starts[0]["log.effective_level"] == "warn"
    assert "db-secret-value" not in r.stdout + r.stderr


def test_deployment_environment_is_on_every_line(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json", DEPLOYMENT_ENVIRONMENT="pilot")
    _write_sample_lines()
    assert [json.loads(line)["deployment.environment"] for line in _lines(capsys)] == ["pilot", "pilot"]


@pytest.mark.parametrize("env", [{}, {"DEPLOYMENT_ENVIRONMENT": ""}, {"DEPLOYMENT_ENVIRONMENT": "   "}],
                         ids=["unset", "empty", "blank"])
def test_deployment_environment_is_left_out_when_not_set(setup_from_env, capsys, env):
    setup_from_env(LOG_FORMAT="json", **env)
    _write_sample_lines()
    lines = _lines(capsys)
    assert len(lines) == 2
    assert not any("deployment.environment" in json.loads(line) for line in lines)


def test_deployment_environment_is_trimmed(setup_from_env, capsys):
    setup_from_env(LOG_FORMAT="json", DEPLOYMENT_ENVIRONMENT=" pilot ")
    _write_sample_lines()
    assert {json.loads(line)["deployment.environment"] for line in _lines(capsys)} == {"pilot"}


def test_text_line_has_the_deployment_environment():
    line = TextFormatter(deployment_environment="dev").format(_record())
    assert re.match(r"\d{4}-.*Z info  app.test: hello world deployment.environment=dev$", line)
