# deleteFile removes the row and the file. The row goes first (commit), so a file that is already
# missing on disk does not turn a done delete into an error; it is logged. Any other error removing
# the file is still reported.

import logging
import os

import app.dependencies

from tests.conftest import DELETE_FILE, auth, gql, new_tenant, stored_file, upload

LIST_FILES = "query($t: String!) { files(tenant: $t) { id } }"


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


def test_delete_file_reports_other_errors_removing_the_file(client, monkeypatch):
    tenant, file = uploaded(client)

    def no_permission(path):
        raise PermissionError(path)

    monkeypatch.setattr(app.dependencies, "delete_file", no_permission)
    r = gql(client, auth([tenant]), DELETE_FILE, {"id": file["id"]})

    assert r.json()["data"] is None and r.json()["errors"], r.text
