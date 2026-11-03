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
# passes only when it is a literal, an id-like name or a class name. Names are split into words
# (snake_case, camelCase, the dots of an access) and compared as whole words against the word list
# all services share; string literals are not scanned for words. A legitimate hit gets an entry in
# ALLOWED (file and finding) with its reason; an entry that no longer matches a hit fails too. A false
# positive is fixed in the scanner, not allowlisted.

import ast
import os
import re
from typing import Iterator, Optional

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LOG_METHODS = {"trace", "debug", "info", "warning", "warn", "error", "exception", "critical", "fatal", "log"}
# The common word list (eegfaktura-dev#45), as written there; several words are one entry
# (api_key, "mail address") and match however the name joins them (api_key, apiKey, apikey).
WORD_LIST = ("password", "passwd", "pwd", "secret", "token", "jwt", "bearer", "authorization", "credential",
             "creds", "cookie", "apikey", "api_key", "iban", "bic", "firstname", "lastname", "vorname",
             "nachname", "name1", "name2", "street", "phone", "email", "mail address", "recipient", "sentto",
             "owner", "accountholder", "username", "userid", "sub", "subject", "payload", "body")
SENSITIVE_WORDS = {re.sub(r"[ _]", "", entry) for entry in WORD_LIST}
_WORD = re.compile(r"[A-Z]+(?![a-z])\d*|[A-Z]?[a-z]+\d*|\d+")
SCALAR = re.compile(r"(^|_)id$|Id$|^method$|^route$|^status(_code)?$")
OBJECT_DUMPS = {"vars", "repr", "ascii", "dir", "locals", "globals", "asdict", "dict", "json", "dumps",
                "model_dump", "model_dump_json", "to_dict", "as_dict"}
TRANSPARENT_CALLS = {"str", "int", "len", "type"}
REPR_FORMAT = re.compile(r"%[-#0 +]*\d*(\.\d+)?[ra]")

# (file, finding): why this value may be logged.
ALLOWED: dict[tuple[str, str], str] = {}


def _is_log_call(node: ast.Call) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "print"
    return (isinstance(func, ast.Attribute) and func.attr in LOG_METHODS
            and "log" in ast.unparse(func.value).lower())


def _path(node: ast.expr) -> Optional[str]:
    # The whole access, user["id"] as user.id; None when it does not start at a plain name.
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base, leaf = _path(node.value), node.attr
    elif isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
            and isinstance(node.slice.value, str):
        base, leaf = _path(node.value), node.slice.value
    else:
        return None
    return f"{base}.{leaf}" if base else None


def words(name: str) -> list[str]:
    # payer_iban -> payer, iban; firstName -> first, name; HTTPAuthorization -> http, authorization
    return [w.lower() for w in _WORD.findall(name)]


def _sensitive(path: str) -> bool:
    # a run of whole words, joined, is on the list: first_name and firstName are "firstname",
    # user.id is "userid" (no user tracking); subscription is not "sub"
    w = words(path)
    return any("".join(w[i:j]) in SENSITIVE_WORDS for i in range(len(w)) for j in range(i + 1, len(w) + 1))


def _literal(text: str) -> Iterator[str]:
    # message text is not scanned for words; only a repr conversion is a finding
    if REPR_FORMAT.search(text):
        yield f"repr of an object: {text}"


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
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", None)
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
        path = _path(node)
        if path is not None and _sensitive(path):
            yield f"sensitive name: {ast.unparse(node)}"
        elif path is None or not SCALAR.search(path.rsplit(".", 1)[-1]):
            yield f"object: {ast.unparse(node)}"


def _extra(node: ast.expr) -> Iterator[str]:
    # The formatter writes only its allowlisted fields; here only names are checked: the keys are
    # field names, the values names reached in the dict.
    if not isinstance(node, ast.Dict):
        yield f"object: extra={ast.unparse(node)}"
        return
    for key in node.keys:
        if isinstance(key, ast.Constant) and isinstance(key.value, str) and _sensitive(key.value):
            yield f"sensitive field: {key.value}"
    for sub in ast.walk(node):
        if isinstance(sub, (ast.Name, ast.Attribute, ast.Subscript)):
            path = _path(sub)
            if path is not None and _sensitive(path):
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
    'logger.info("user %s", user.id)',
    'logger.info("user %s", user["id"])',
    'logger.info(f"user {user.id}")',
    'logger.info("user %s", str(request.state.current_user.id))',
    'logger.info("user %s", users[0].id)',
    'logger.info("user %s", get_user().id)',
    'logger.info("x", extra={"event.action": user.id})',
    'logger.info("x", extra={"event.action": user["id"]})',
    'logger.info("upload %s", file.filename)',
    'logger.info("upload %s", name)',
    'logger.info("subject %s", claims.sub)',
    'logger.info("x %s", owner_id)',
    'logger.info("x %s", recipientId)',
    'logger.info("x %s", str(claims.subject))',
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
    'logger.info("file %s", metadata["file"].id)',
    'logger.info("file %s", str(metadata["storage_id"]))',
    'logger.warning("failed: %s", type(e).__name__)',
    'logger.info("%s %s %s", scope["method"], route or "-", status)',
    'logger.info("x", exc_info=True)',
    'logger.info("x", extra={"event.action": "http.access", "http.response.status_code": status})',
    '_graphql_logger.log(logging.ERROR, "GraphQL error")',
    'logger.info("e-mail not sent, token refused")',
    'logger.info("subscription %s", subscription_id)',
    'logger.info("x", extra={"event.action": "user.email.sent"})',
    'catalog.size(email)',
    'other.info(email)',
])
def test_the_scan_leaves_alone(line):
    assert findings(line) == []


@pytest.mark.parametrize("name", ["firstName", "first_name", "FIRSTNAME", "api_key", "apiKey", "mail_address",
                                  "mailAddress", "name1", "accountHolder", "sent_to", "HTTPAuthorization",
                                  "user.id", "current_user.id", "claims.sub", "request.body", "jwt", "iban"])
def test_the_word_list_matches_whole_words(name):
    assert _sensitive(name)


@pytest.mark.parametrize("name", ["subscription", "file_id", "tokenizer", "bodyguard", "streetwise", "nickname",
                                  "file.name", "storage.id", "tenant", "subtenant_id"])
def test_the_word_list_leaves_other_words_alone(name):
    assert not _sensitive(name)
