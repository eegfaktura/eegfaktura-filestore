# The single-file queries (file, contract, invoice) and the addFile result through the real application.

import uuid

from tests.conftest import auth, gql, new_tenant, upload

FILE_FIELDS = "id tenant userId name fileCategory fileDownloadUri createdAt attributes { key value }"


def uploaded(client, tenant, category):
    r = upload(client, tenant, auth([tenant]), category=category)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_file_returns_the_stored_file(client):
    tenant = new_tenant()
    file_id = uploaded(client, tenant, "contract")

    r = gql(client, auth([tenant]), f"query($id: UUID!) {{ file(id: $id) {{ {FILE_FIELDS} }} }}", {"id": file_id})

    file = r.json()["data"]["file"]
    assert (file["id"], file["tenant"], file["name"], file["fileCategory"]) == (file_id, tenant, "vertrag", "contract")
    assert uuid.UUID(file["userId"])
    assert file["fileDownloadUri"].endswith(f"/filestore/{file_id}")
    assert {"key": "media_type", "value": "application/pdf"} in file["attributes"]


def test_contract_and_invoice_return_a_file_of_their_category_only(client):
    tenant = new_tenant()
    contract_id = uploaded(client, tenant, "contract")
    invoice_id = uploaded(client, tenant, "invoice")
    query = "query($id: UUID!) { contract(id: $id) { id fileCategory } invoice(id: $id) { id fileCategory } }"

    for file_id, own, other in ((contract_id, "contract", "invoice"), (invoice_id, "invoice", "contract")):
        r = gql(client, auth([tenant]), query, {"id": file_id})

        assert r.json()["data"][own] == {"id": file_id, "fileCategory": own}, r.text
        assert r.json()["data"][other] is None, r.text
        assert [e["path"] for e in r.json()["errors"]] == [[other]], r.text

