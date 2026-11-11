# Test setup: a throw-away RSA keypair (the public key goes to JWT_KEY_FILE, the private key only
# signs test tokens in memory), a temporary FILESTORE_LOCAL_BASE_DIR, and the database from the DB_*
# environment variables, migrated beforehand (alembic upgrade head) — in CI the full job's PostgreSQL.
# app.config reads the environment at import time, so everything is set before the app is imported.

import atexit
import json
import os
import shutil
import tempfile
import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

_tmp = tempfile.mkdtemp(prefix="filestore-test-")
atexit.register(shutil.rmtree, _tmp, ignore_errors=True)
_pub_key_file = os.path.join(_tmp, "jwt_pub_key.pem")
with open(_pub_key_file, "wb") as f:
    f.write(_private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

os.environ["JWT_KEY_FILE"] = _pub_key_file
os.environ["FILESTORE_LOCAL_BASE_DIR"] = os.path.join(_tmp, "data")
os.makedirs(os.path.join(_tmp, "data", "tmp"))

from fastapi.testclient import TestClient  # noqa: E402

from app.app import create_app  # noqa: E402
from app.config import settings  # noqa: E402

# Helpers shared by several test modules; a test module imports them from here, not from another test module.
PDF = b"%PDF-1.4\n% filestore test\n"
ADD_FILE = ("mutation($file: Upload!, $t: String!, $a: [AttributeInput!]) {"
            " addFile(file: $file, name: \"x\", fileCategory: \"contract\", tenant: $t, attributes: $a) {"
            " __typename ... on AddFileError { message } } }")
DELETE_FILE = ("mutation($id: UUID!) { deleteFile(fileId: $id) {"
               " __typename ... on DeleteFile { id } ... on DeleteFileError { message } } }")


def make_token(tenants, **claims):
    payload = {"tenant": tenants, "aud": "account", "exp": int(time.time()) + 300}
    payload.update(claims)
    return jwt.encode(payload, _private_key, algorithm="RS256")


def auth(tenants):
    return {"Authorization": f"Bearer {make_token(tenants)}"}


def new_tenant() -> str:
    # The tenant columns are VARCHAR(8); a fresh tenant per test keeps tests independent of leftovers.
    return "T" + uuid.uuid4().hex[:7].upper()


def upload(client, tenant, headers, category="contract"):
    return client.post(
        f"/filestore/upload/{category}/{tenant}/{uuid.uuid4()}",
        headers=headers,
        files={"file": ("vertrag.pdf", PDF, "application/pdf")},
    )


def gql(client, headers, query, variables=None):
    return client.post("/graphql", headers=headers, json={"query": query, "variables": variables or {}})


def add_file(client, tenant, attributes=None, filename="x.pdf", query=ADD_FILE, user_id=None):
    # the query declares $file, $t, $a and, when a user id is given, $u; without one $u is left out
    variables = {"file": None, "t": tenant, "a": attributes or []} | ({"u": user_id} if user_id else {})
    return client.post(
        "/graphql",
        headers=auth([tenant]),
        data={"operations": json.dumps({"query": query, "variables": variables}),
              "map": json.dumps({"0": ["variables.file"]})},
        files={"0": (filename, PDF, "application/pdf")},
    )


def stored_file(file_id):
    for d, _, names in os.walk(settings.FILESTORE_LOCAL_BASE_DIR):
        if file_id in names:
            return os.path.join(d, file_id)
    return None


@pytest.fixture(scope="session")
def client():
    # One client for the whole session: the async database engine's connections belong to the event
    # loop of the client's portal.
    with TestClient(create_app()) as c:
        yield c
