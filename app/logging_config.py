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

# The one logging setup of the service: every log line (the application's, uvicorn's, alembic's)
# goes through the handler configured here. LOG_FORMAT=json writes one ECS-named JSON object per
# line on stdout, LOG_FORMAT=text the same fields as one readable line. Only the fields listed
# below are written; anything else a log call passes in `extra` is dropped (never-log guard).

import contextvars
import json
import logging
import logging.config
from datetime import datetime, timezone
from typing import Optional

from app.config import settings

SERVICE_NAME = "eegfaktura-filestore"

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

LEVELS = {"trace": TRACE, "debug": logging.DEBUG, "info": logging.INFO,
          "warn": logging.WARNING, "warning": logging.WARNING, "error": logging.ERROR}
FORMATS = ("json", "text")

# Per-request fields, set by the access-log middleware and the token check; on every line of the request.
CONTEXT_FIELDS = ("request.id", "trace.id", "span.id", "tenant.id", "client.id", "graphql.operation.name")
# Fields a log call may pass in `extra`.
EXTRA_FIELDS = ("event.action", "event.outcome", "event.duration", "http.request.method", "http.route",
                "http.response.status_code")

log_context: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("log_context", default=None)


def parse_level(value: str) -> int:
    level = LEVELS.get((value or "").strip().lower())
    if level is None:
        raise ValueError(f"LOG_LEVEL={value!r} is not one of {', '.join(LEVELS)}")
    return level


def parse_format(value: str) -> str:
    fmt = (value or "").strip().lower()
    if fmt not in FORMATS:
        raise ValueError(f"LOG_FORMAT={value!r} is not one of {', '.join(FORMATS)}")
    return fmt


def _level_name(levelno: int) -> str:
    if levelno <= TRACE:
        return "trace"
    if levelno <= logging.DEBUG:
        return "debug"
    if levelno <= logging.INFO:
        return "info"
    if levelno <= logging.WARNING:
        return "warn"
    return "error"


def request_log_context(request) -> dict:
    """The per-request field dict the middleware put on request.state (a throw-away dict without it)."""
    return getattr(request.state, "log_context", None) or {}


class _Formatter(logging.Formatter):
    def __init__(self, service_version: str = "dev"):
        super().__init__()
        self.service_version = service_version

    def fields(self, record: logging.LogRecord) -> dict:
        out = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "log.level": _level_name(record.levelno),
            "log.logger": record.name,
            "service.name": SERVICE_NAME,
            "service.version": self.service_version,
        }
        ctx = log_context.get() or {}
        for key in CONTEXT_FIELDS:
            if ctx.get(key) is not None:
                out[key] = ctx[key]
        for key in EXTRA_FIELDS:
            value = record.__dict__.get(key)
            if value is not None:
                out[key] = value
        out["message"] = record.getMessage()
        if record.exc_info and record.exc_info[0] is not None:
            out["error.type"] = record.exc_info[0].__name__
            out["error.message"] = str(record.exc_info[1])
            out["error.stack_trace"] = self.formatException(record.exc_info)
        return out


class JsonFormatter(_Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(self.fields(record), ensure_ascii=False, default=str)


class TextFormatter(_Formatter):
    _HEAD = ("@timestamp", "log.level", "log.logger", "message", "service.name", "service.version",
             "error.stack_trace")

    def format(self, record: logging.LogRecord) -> str:
        f = self.fields(record)
        line = f"{f['@timestamp']} {f['log.level']:<5} {f['log.logger']}: {f['message']}"
        for key, value in f.items():
            if key not in self._HEAD:
                value = str(value)
                if not value or any(c in value for c in ' "=\n'):
                    value = json.dumps(value, ensure_ascii=False)
                line += f" {key}={value}"
        if "error.stack_trace" in f:
            line += "\n" + f["error.stack_trace"]
        return line


def dict_config(level: int, fmt: str, service_version: str) -> dict:
    formatter = JsonFormatter if fmt == "json" else TextFormatter
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {"()": formatter, "service_version": service_version}},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
            "null": {"class": "logging.NullHandler"},
        },
        "loggers": {
            # uvicorn's own lines go to the root handler; its access line is replaced by the
            # application's (app.access_log: route template, no client address, no query).
            "uvicorn": {"handlers": [], "propagate": True},
            "uvicorn.error": {"handlers": [], "propagate": True},
            "uvicorn.access": {"handlers": ["null"], "propagate": False},
        },
        "root": {"level": level, "handlers": ["stdout"]},
    }


def configure_logging() -> None:
    """Apply the logging setup from the settings; an unknown LOG_LEVEL or LOG_FORMAT stops the start."""
    level = parse_level(settings.LOG_LEVEL)
    fmt = parse_format(settings.LOG_FORMAT)
    logging.config.dictConfig(dict_config(level, fmt, settings.SERVICE_VERSION))
