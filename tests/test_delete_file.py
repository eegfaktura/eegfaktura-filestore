# deleteFile removes the row and the file. The row goes first (commit), so a file that cannot be
# removed afterwards does not turn a done delete into an error; it is logged as an orphan.

import logging
import os

from app.config import settings
from tests.conftest import auth, new_tenant
from tests.test_security import gql, upload

DELETE_FILE = ("mutation($id: UUID!) { deleteFile(fileId: $id) {"
               " __typename ... on DeleteFile { id } ... on DeleteFileError { message } } }")
LIST_FILES = "query($t: String!) { files(tenant: $t) { id } }"


def stored_file(file_id):
    for d, _, names in os.walk(settings.FILESTORE_LOCAL_BASE_DIR):
        if file_id in names:
            return os.path.join(d, file_id)
    return None


def uploaded(client):
    tenant = new_tenant()
    r = upload(client, tenant, auth([tenant]))
    assert r.status_code == 200, r.text
    return tenant, {"id": r.json()["id"]}


def test_delete_file_removes_row_and_file(client):
    tenant, file = uploaded(client)
    path = stored_file(file["id"])
    assert path is not None

    r = gql(client, auth([tenant]), DELETE_FILE, {"id": file["id"]})

    assert r.json()["data"]["deleteFile"] == {"__typename": "DeleteFile", "id": file["id"]}, r.text
    assert gql(client, auth([tenant]), LIST_FILES, {"t": tenant}).json()["data"]["files"] == []
    assert not os.path.exists(path)


def test_delete_file_whose_file_is_gone_still_deletes_and_logs(client, caplog):
    tenant, file = uploaded(client)
    os.remove(stored_file(file["id"]))

    with caplog.at_level(logging.WARNING, logger="app.graphql.resolvers.file_resolver"):
        r = gql(client, auth([tenant]), DELETE_FILE, {"id": file["id"]})

    assert r.json()["data"]["deleteFile"] == {"__typename": "DeleteFile", "id": file["id"]}, r.text
    assert gql(client, auth([tenant]), LIST_FILES, {"t": tenant}).json()["data"]["files"] == []
    assert any(file["id"] in m and "FileNotFoundError" in m for m in caplog.messages), caplog.messages
