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
import re
import sys
from datetime import datetime, timezone
from typing import Optional

SERVICE_NAME = "eegfaktura-filestore"

TRACE = 5
logging.addLevelName(TRACE, "TRACE")

LEVELS = {"trace": TRACE, "debug": logging.DEBUG, "info": logging.INFO,
          "warn": logging.WARNING, "warning": logging.WARNING, "error": logging.ERROR}
FORMATS = ("json", "text")

# Per-request fields, set by the access-log middleware and the token check; on every line of the request.
CONTEXT_FIELDS = ("request.id", "trace.id", "span.id", "tenant.id", "client.id", "graphql.operation.name")
# Fields a log call may pass in `extra`.
EXTRA_FIELDS = ("log.effective_level", "event.action", "event.outcome", "event.duration", "http.request.method", "http.route",
                "http.response.status_code", "error.type", "error.stack_trace", "graphql.error.path")

log_context: contextvars.ContextVar[Optional[dict]] = contextvars.ContextVar("log_context", default=None)


def parse_level(value: str) -> int:
    # empty (set but blank) means the default
    level = LEVELS.get((value or "").strip().lower() or "info")
    if level is None:
        raise ValueError(f"LOG_LEVEL={value!r} is not one of {', '.join(LEVELS)}")
    return level


def parse_format(value: str) -> str:
    fmt = (value or "").strip().lower() or "text"
    if fmt not in FORMATS:
        raise ValueError(f"LOG_FORMAT={value!r} is not one of {', '.join(FORMATS)}")
    return fmt


def error_type(exc_type: type) -> str:
    """error.type: the fully qualified class name (module and qualified name), e.g.
    sqlalchemy.exc.OperationalError or builtins.KeyError."""
    return f"{exc_type.__module__}.{exc_type.__qualname__}"


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


def current_log_context() -> dict:
    """The request's field dict set by the access-log middleware (a throw-away dict outside a request).

    The one source of the per-request fields: the middleware sets it, the token check adds to it,
    the formatter and the access line read it. Keys starting with "_" are internal, never written.
    """
    ctx = log_context.get()
    return ctx if ctx is not None else {}


# tenant.id (all services): letters, digits, "_" and "-", up to 64, after upper-casing
_TENANT_ID = re.compile(r"[A-Z0-9][A-Z0-9_-]{0,63}")


def record_tenant_check(tenant: Optional[str], allowed: bool) -> None:
    """Note a tenant check in the request's context: tenant.id only when every check of the request
    passed and all were for the same tenant; a refused check marks the request as refused.
    `tenant` is the checked stem (app.auth); the one place of the tenant.id rule of all services:
    stripped and upper-cased it must match _TENANT_ID, otherwise the check counts as one whose tenant
    is not logged (a passed check then leaves tenant.id out)."""
    tenant = (tenant or "").strip().upper()
    if not _TENANT_ID.fullmatch(tenant):
        tenant = None
    ctx = current_log_context()
    if allowed:
        ctx.setdefault("_tenants", set()).add(tenant)
    else:
        ctx["_refused"] = True
    tenants = ctx.get("_tenants", set())
    if not ctx.get("_refused") and len(tenants) == 1 and None not in tenants:
        ctx["tenant.id"] = next(iter(tenants))
    else:
        ctx.pop("tenant.id", None)


_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


def _escape_control(text: str) -> str:
    return _CONTROL.sub(lambda m: m.group().encode("unicode_escape").decode("ascii"), text)


class _Formatter(logging.Formatter):
    def __init__(self, service_version: str = "dev", deployment_environment: str = ""):
        super().__init__()
        self.service_version = service_version
        self.deployment_environment = deployment_environment

    def fields(self, record: logging.LogRecord) -> dict:
        out = {
            "@timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "log.level": _level_name(record.levelno),
            "log.logger": record.name,
            "service.name": SERVICE_NAME,
            "service.version": self.service_version,
        }
        if self.deployment_environment:
            out["deployment.environment"] = self.deployment_environment
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
            out["error.type"] = error_type(record.exc_info[0])
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
        # one record, one line: control characters (a message's newlines, ...) are escaped
        line = f"{f['@timestamp']} {f['log.level']:<5} {f['log.logger']}: {_escape_control(f['message'])}"
        for key, value in f.items():
            if key not in self._HEAD:
                value = str(value)
                if not value or any(c in value for c in ' "=') or _CONTROL.search(value):
                    value = json.dumps(value, ensure_ascii=False)
                line += f" {key}={value}"
        if "error.stack_trace" in f:
            line += "\n" + f["error.stack_trace"]
        return line


def dict_config(level: int, fmt: str, service_version: str, deployment_environment: str = "") -> dict:
    formatter = JsonFormatter if fmt == "json" else TextFormatter
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": {"()": formatter, "service_version": service_version,
                                   "deployment_environment": deployment_environment}},
        "handlers": {
            "stdout": {"class": "logging.StreamHandler", "formatter": "default", "stream": "ext://sys.stdout"},
            "null": {"class": "logging.NullHandler"},
        },
        "loggers": {
            # uvicorn's own lines go to the root handler; its access line is replaced by the
            # application's (app.access_log: route template, no client address, no query).
            "uvicorn": {"handlers": [], "propagate": True},
            # never below debug: uvicorn logs connections ("HTTP connection made", client IP:port) at trace
            "uvicorn.error": {"handlers": [], "propagate": True, "level": max(level, logging.DEBUG)},
            "uvicorn.access": {"handlers": ["null"], "propagate": False},
            # the access and start lines are written at info whatever LOG_LEVEL says
            "app.access": {"level": logging.INFO},
            "app.start": {"level": logging.INFO},
        },
        "root": {"level": level, "handlers": ["stdout"]},
    }


def configure_logging(settings) -> None:
    """Apply the logging setup from the settings (app.config.Settings); an unknown LOG_LEVEL or
    LOG_FORMAT stops the start; an empty value means the default."""
    level = parse_level(settings.LOG_LEVEL)
    fmt = parse_format(settings.LOG_FORMAT)
    logging.config.dictConfig(dict_config(level, fmt, settings.SERVICE_VERSION, settings.DEPLOYMENT_ENVIRONMENT))
    logging.captureWarnings(True)
    sys.excepthook = _log_uncaught


def _log_uncaught(exc_type, exc, tb) -> None:
    # An exception nothing caught (alembic not reaching the database, a bad JWT key file at import)
    # ends the process: one line through the setup above instead of a plain traceback on stderr.
    logging.getLogger("app.uncaught").critical("uncaught exception, the process stops", exc_info=(exc_type, exc, tb))


def log_service_start() -> None:
    """The one start-up line with the effective log level (service.version is on every line). Written
    at info whatever LOG_LEVEL says (app.start has level info, see dict_config), so that every
    deployment shows since when it runs and how; nothing from the settings but these."""
    level = _level_name(logging.getLogger().getEffectiveLevel())
    logging.getLogger("app.start").info("service start", extra={
        "event.action": "service.start", "log.effective_level": level})
