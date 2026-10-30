# A failed upload leaves nothing behind: attributes the table does not take are rejected before
# anything is written, and when the commit fails anyway, neither the stored nor the temporary file
# remains on disk.

import json
import os
import uuid

import pytest
from sqlalchemy.exc import DBAPIError

from app.config import settings
from tests.conftest import auth, new_tenant
from tests.test_security import PDF, gql, upload

ADD_FILE = ("mutation($file: Upload!, $t: String!, $a: [AttributeInput!]) {"
            " addFile(file: $file, name: \"x\", fileCategory: \"contract\", tenant: $t, attributes: $a) {"
            " __typename ... on AddFileError { message } } }")
LIST_FILES = "query($t: String!) { files(tenant: $t) { id } }"


def files_on_disk():
    return {os.path.join(d, f) for d, _, names in os.walk(settings.FILESTORE_LOCAL_BASE_DIR) for f in names}


def add_file(client, tenant, attributes=None, filename="x.pdf"):
    variables = {"file": None, "t": tenant, "a": attributes or []}
    return client.post(
        "/graphql",
        headers=auth([tenant]),
        data={"operations": json.dumps({"query": ADD_FILE, "variables": variables}),
              "map": json.dumps({"0": ["variables.file"]})},
        files={"0": (filename, PDF, "application/pdf")},
    )


def tenant_with_one_file(client):
    # One regular file, so the tenant's storage and container directories exist
    tenant = new_tenant()
    assert upload(client, tenant, auth([tenant])).status_code == 200
    return tenant


def file_rows(client, tenant):
    return gql(client, auth([tenant]), LIST_FILES, {"t": tenant}).json()["data"]["files"]


@pytest.mark.parametrize("attributes, message", [
    ([{"key": "member", "value": "1"}, {"key": "member", "value": "2"}], "Duplicate Attribute \"member\""),
    ([{"key": "k" * 129, "value": "1"}], "Invalid Attribute: key up to 128, value up to 512 characters"),
    ([{"key": "member", "value": "v" * 513}], "Invalid Attribute: key up to 128, value up to 512 characters"),
], ids=["duplicate-key", "key-too-long", "value-too-long"])
def test_graphql_upload_with_invalid_attributes_stores_nothing(client, attributes, message):
    tenant = tenant_with_one_file(client)
    rows_before, disk_before = file_rows(client, tenant), files_on_disk()

    r = add_file(client, tenant, attributes)

    assert r.status_code == 200, r.text
    assert r.json()["data"]["addFile"] == {"__typename": "AddFileError", "message": message}
    assert file_rows(client, tenant) == rows_before
    assert files_on_disk() == disk_before


def test_graphql_upload_failing_at_commit_leaves_no_file(client):
    # The file extension (attribute value, up to 512 characters) only fails at the commit
    tenant = tenant_with_one_file(client)
    rows_before, disk_before = file_rows(client, tenant), files_on_disk()

    r = add_file(client, tenant, filename="x." + "p" * 600)

    assert r.json()["data"] is None and r.json()["errors"][0]["path"] == ["addFile"], r.text
    assert file_rows(client, tenant) == rows_before
    assert files_on_disk() == disk_before


def test_rest_upload_failing_at_commit_leaves_no_file(client):
    tenant = tenant_with_one_file(client)
    disk_before = files_on_disk()

    with pytest.raises(DBAPIError):
        client.post(f"/filestore/upload/contract/{tenant}/{uuid.uuid4()}",
                    headers=auth([tenant]),
                    files={"file": ("x." + "p" * 600, PDF, "application/pdf")})

    assert files_on_disk() == disk_before


def test_graphql_upload_with_too_long_name_stores_nothing(client):
    tenant = tenant_with_one_file(client)
    rows_before, disk_before = file_rows(client, tenant), files_on_disk()
    query = ADD_FILE.replace('name: "x"', 'name: "' + "n" * 129 + '"')
    assert query != ADD_FILE

    r = client.post(
        "/graphql",
        headers=auth([tenant]),
        data={"operations": json.dumps({"query": query, "variables": {"file": None, "t": tenant, "a": []}}),
              "map": json.dumps({"0": ["variables.file"]})},
        files={"0": ("x.pdf", PDF, "application/pdf")},
    )

    assert r.json()["data"]["addFile"] == {"__typename": "AddFileError",
                                           "message": "Invalid name: up to 128 characters"}, r.text
    assert file_rows(client, tenant) == rows_before
    assert files_on_disk() == disk_before
