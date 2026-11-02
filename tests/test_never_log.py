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

# Never-log scan: reads the source (app/, main.py, alembic/) and fails on a log call that names
# personal data or secrets, or that writes a whole object. Values are denied by default: a value
# passes only when it is a literal, an id-like name or a class name. A legitimate hit gets an entry
# in ALLOWED with its reason; an entry that no longer matches a hit fails too.

import ast
import os
import re
from typing import Iterator, Optional

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_METHODS = {"trace", "debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
# Matches inside identifiers (payer_iban, userEmail) as well as in message text ("e-mail", "first name").
SENSITIVE = re.compile(
    r"first[ _.-]?name|last[ _.-]?name|sur[ _.-]?name|family[ _.-]?name|given[ _.-]?name|full[ _.-]?name"
    r"|e-?mail|iban|pass[ _.-]?word|passwd|pwd|secret|token|authorization|bearer|credential|cookie"
    r"|api[ _.-]?key|private[ _.-]?key|user[ _.-]?name|user[ _.-]?id|file[ _.-]?name", re.IGNORECASE)
# Too short to match inside other words: only as the whole identifier. "name" is a file's or a
# person's name here, "sub" the Keycloak user id (no user tracking, W-261008-ca2).
SENSITIVE_EXACT = {"name", "sub"}
SCALAR = re.compile(r"(^|_)id$|Id$|^method$|^route$|^status(_code)?$")
OBJECT_DUMPS = {"vars", "repr", "ascii", "dir", "locals", "globals", "asdict", "dict", "json", "dumps",
                "model_dump", "model_dump_json", "to_dict", "as_dict"}
TRANSPARENT_CALLS = {"str", "int", "len", "type"}
REPR_FORMAT = re.compile(r"%[-#0 +]*\d*(\.\d+)?[ra]")

# (file, finding): why this value may be logged.
ALLOWED = {
    ("app/auth.py", "object: e"):
        "PyJWT's exception text names the failed check, it carries no claim or token value",
    ("app/rest/routers/filestore.py", "object: settings.FILESTORE_LOCAL_BASE_DIR"):
        "the configured base directory of the on-disk path; the rest of the path is UUIDs only",
}


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "print"
    return (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS
            and "log" in ast.unparse(func.value).lower())


def _sensitive(identifier: str) -> bool:
    return identifier in SENSITIVE_EXACT or SENSITIVE.search(identifier) is not None


def _literal(text: str) -> Iterator[str]:
    if SENSITIVE.search(text):
        yield f"sensitive name in text: {text}"
    if REPR_FORMAT.search(text):
        yield f"repr of an object: {text}"


def _leaf(node: ast.expr) -> Optional[str]:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
        return str(node.slice.value)
    return None


def _value(node: ast.expr) -> Iterator[str]:
    if isinstance(node, ast.Constant):
        if isinstance(node.value, str):
            yield from _literal(node.value)
    elif isinstance(node, ast.JoinedStr):
        for part in node.values:
            yield from _value(part)
    elif isinstance(node, ast.FormattedValue):
        if node.conversion in (ord("r"), ord("a")):
            yield f"repr of an object: {ast.unparse(node)}"
        yield from _value(node.value)
    elif isinstance(node, ast.BinOp):
        yield from _value(node.left)
        yield from _value(node.right)
    elif isinstance(node, ast.BoolOp):
        for operand in node.values:
            yield from _value(operand)
    elif isinstance(node, ast.IfExp):
        yield from _value(node.body)
        yield from _value(node.orelse)
    elif isinstance(node, ast.Call):
        name = _leaf(node.func)
        if name in OBJECT_DUMPS:
            yield f"dump of an object: {ast.unparse(node)}"
        elif name in TRANSPARENT_CALLS and node.args:
            yield from _value(node.args[0])
        else:
            yield f"object: {ast.unparse(node)}"
    elif isinstance(node, ast.Attribute) and node.attr == "__name__":
        return  # a class name
    elif isinstance(node, ast.Attribute) and node.attr == "__dict__":
        yield f"dump of an object: {ast.unparse(node)}"
    else:
        leaf = _leaf(node)
        if leaf is not None and _sensitive(leaf):
            yield f"sensitive name: {ast.unparse(node)}"
        elif leaf is None or not SCALAR.search(leaf):
            yield f"object: {ast.unparse(node)}"


def _extra(node: ast.expr) -> Iterator[str]:
    # The formatter writes only its allowlisted fields; here only names are checked.
    if not isinstance(node, ast.Dict):
        yield f"object: extra={ast.unparse(node)}"
        return
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            yield from _literal(sub.value)
        elif isinstance(sub, (ast.Name, ast.Attribute)) and _sensitive(_leaf(sub)):
            yield f"sensitive name: {ast.unparse(sub)}"


def findings(source: str) -> list[tuple[int, str]]:
    out = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _is_log_call(node):
            args = node.args
            if isinstance(node.func, ast.Attribute) and node.func.attr == "log":
                args = args[1:]  # the level
            for arg in args:
                out += [(node.lineno, f) for f in _value(arg)]
            for keyword in node.keywords:
                if keyword.arg == "extra":
                    out += [(node.lineno, f) for f in _extra(keyword.value)]
    return out


def source_files() -> list[str]:
    paths = ["main.py"]
    for top in ("app", "alembic"):
        for directory, _, names in os.walk(os.path.join(REPO, top)):
            paths += [os.path.relpath(os.path.join(directory, n), REPO).replace(os.sep, "/")
                      for n in names if n.endswith(".py")]
    return paths


def scan() -> list[tuple[str, int, str]]:
    hits = []
    for path in source_files():
        with open(os.path.join(REPO, path), encoding="utf-8") as f:
            hits += [(path, line, finding) for line, finding in findings(f.read())]
    return hits


def test_the_source_logs_nothing_it_must_not():
    hits = [f"{path}:{line}: {finding}" for path, line, finding in scan() if (path, finding) not in ALLOWED]
    assert hits == []


def test_every_allowlist_entry_has_a_reason_and_is_still_needed():
    found = {(path, finding) for path, _, finding in scan()}
    assert all(reason.strip() for reason in ALLOWED.values())
    assert set(ALLOWED) <= found


def test_the_scan_sees_the_source():
    calls = 0
    for path in source_files():
        with open(os.path.join(REPO, path), encoding="utf-8") as f:
            calls += sum(isinstance(n, ast.Call) and _is_log_call(n) for n in ast.walk(ast.parse(f.read())))
    assert {"main.py", "app/auth.py", "app/db/session.py"} <= set(source_files())
    assert calls >= 6


@pytest.mark.parametrize("line", [
    'logger.info("member %s", firstname)',
    'logger.info("member %s", member.last_name)',
    'logger.info("sent to %s", user["email"])',
    'logger.warning("iban: " + str(payer_iban))',
    'logger.error(f"login with {password}")',
    'logger.debug("got %s", access_token)',
    'logger.info("user %s", user_id)',
    'logger.info("upload %s", file.filename)',
    'logger.info("upload %s", name)',
    'logger.info("subject %s", claims.sub)',
    'logger.info("e-mail not sent")',
    'logger.info("x", extra={"user.email": value})',
    'logger.info("x", extra={"event.action": token})',
    'logger.info("x", extra=fields)',
    'logging.getLogger("x").info("%s", secret)',
    'self.log.info("%s", secret)',
    '_graphql_logger.log(logging.INFO, "%s", password)',
    'print(password)',
    'logger.info("claims %s", claims)',
    'logger.info("claims %r", file_id)',
    'logger.info(f"claims {file_id!r}")',
    'logger.info(claims)',
    'logger.info("%s", str(payload))',
    'logger.info("%s", vars(file))',
    'logger.info("%s", file.__dict__)',
    'logger.info("%s", file.model_dump())',
    'logger.info("%s", file.as_dict())',
    'logger.info("%s", repr(file_id))',
    'logger.info("%s", json.dumps(body))',
    'logger.info("%s", row or file_id)',
    'logger.info("%s", convert(file_id))',
    'logger.info("%s", items[0])',
])
def test_the_scan_finds(line):
    assert findings(line) != []


@pytest.mark.parametrize("line", [
    'logger.info("started")',
    'logger.warning("file %s in %s", file.id, storage.id)',
    'logger.info("file %s", file_id)',
    'logger.info("file %s", str(metadata["storage_id"]))',
    'logger.warning("failed: %s", type(e).__name__)',
    'logger.info("%s %s %s", scope["method"], route or "-", status)',
    'logger.info("x", exc_info=True)',
    'logger.info("x", extra={"event.action": "http.access", "http.response.status_code": status})',
    '_graphql_logger.log(logging.ERROR, "GraphQL error")',
    'catalog.size(email)',
    'other.info(email)',
])
def test_the_scan_leaves_alone(line):
    assert findings(line) == []
