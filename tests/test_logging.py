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
# the applied setup (in a subprocess, so the test run's own logging stays untouched).

import json
import logging
import os
import re
import subprocess
import sys

import pytest

from app import logging_config
from app.logging_config import JsonFormatter, TextFormatter, log_context, parse_format, parse_level

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _record(level=logging.INFO, msg="hello %s", args=("world",), exc_info=None, **extra):
    record = logging.LogRecord("app.test", level, __file__, 1, msg, args, exc_info)
    record.__dict__.update(extra)
    return record


@pytest.mark.parametrize("value,level", [
    ("trace", logging_config.TRACE), ("debug", logging.DEBUG), ("INFO", logging.INFO),
    ("warn", logging.WARNING), ("warning", logging.WARNING), (" error ", logging.ERROR),
])
def test_known_levels_are_accepted(value, level):
    assert parse_level(value) == level


@pytest.mark.parametrize("value", ["", "verbose", "critical", "5"])
def test_an_unknown_level_is_refused(value):
    with pytest.raises(ValueError, match="LOG_LEVEL"):
        parse_level(value)


def test_formats():
    assert parse_format("JSON") == "json"
    assert parse_format("text") == "text"
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
    assert doc["error.type"] == "KeyError"
    assert doc["error.message"] == "'missing'"
    assert "Traceback" in doc["error.stack_trace"]


def test_text_line_quotes_values_with_spaces():
    token = log_context.set({"request.id": "r1", "tenant.id": "RC 1"})
    try:
        line = TextFormatter().format(_record())
    finally:
        log_context.reset(token)
    assert re.match(r"\d{4}-.*Z info  app.test: hello world request.id=r1 tenant.id=\"RC 1\"$", line)


def _run(code, **env):
    own = ("LOG_LEVEL", "APP_LOG_LEVEL", "LOG_FORMAT", "SERVICE_VERSION")
    full_env = {k: v for k, v in os.environ.items() if k not in own}
    full_env.update(env)
    return subprocess.run([sys.executable, "-c", code], cwd=REPO, env=full_env,
                          capture_output=True, text=True, timeout=60)


_SETUP = ("import logging; from app.logging_config import configure_logging; configure_logging(); "
          "logging.getLogger('uvicorn.error').info('started'); "
          "logging.getLogger('uvicorn.access').info('127.0.0.1 GET /x?q=1'); "
          "logging.getLogger('app.x').debug('dbg'); logging.getLogger('app.x').info('app line')")


def test_the_applied_setup_writes_one_json_object_per_line_and_drops_uvicorns_access_line():
    r = _run(_SETUP, LOG_FORMAT="json", LOG_LEVEL="info", SERVICE_VERSION="9.9.9")
    assert r.returncode == 0, r.stderr
    docs = [json.loads(line) for line in r.stdout.splitlines()]
    assert [(d["log.logger"], d["message"]) for d in docs] == [("uvicorn.error", "started"), ("app.x", "app line")]
    assert {d["service.version"] for d in docs} == {"9.9.9"}
    assert r.stderr == ""


def test_app_log_level_is_still_read_when_log_level_is_not_set():
    r = _run(_SETUP, LOG_FORMAT="json", APP_LOG_LEVEL="debug")
    assert r.returncode == 0, r.stderr
    assert "dbg" in [json.loads(line)["message"] for line in r.stdout.splitlines()]


def test_log_level_wins_over_app_log_level():
    r = _run("from app.config import settings; print(settings.LOG_LEVEL)", LOG_LEVEL="warn", APP_LOG_LEVEL="debug")
    assert r.stdout.strip() == "warn"


def test_an_unknown_log_level_stops_the_start():
    r = _run(_SETUP, LOG_LEVEL="verbose")
    assert r.returncode != 0
    assert "LOG_LEVEL='verbose'" in r.stderr
