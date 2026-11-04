# The single-file queries (file, contract, invoice) and the addFile result through the real application.

import json
import uuid

from tests.conftest import PDF, auth, gql, new_tenant, upload

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


def test_add_file_returns_the_user_id_and_the_stored_attributes(client):
    tenant = new_tenant()
    user_id = str(uuid.uuid4())
    query = ("mutation($file: Upload!, $t: String!, $u: UUID, $a: [AttributeInput!]) {"
             " addFile(file: $file, name: \"x\", fileCategory: \"contract\", tenant: $t, userId: $u, attributes: $a) {"
             " __typename ... on AddFile { userId attributes { key value } } } }")
    stored = [{"key": "orig_file_name", "value": "x"}, {"key": "file_extension", "value": "pdf"},
              {"key": "media_type", "value": "application/pdf"}, {"key": "category_tag", "value": "user"},
              {"key": "file_bytes", "value": str(len(PDF))}]

    def add(user):
        # without a user id the variable is left out (the argument is declared UUID!, with a default)
        variables = {"file": None, "t": tenant, "a": [{"key": "category_tag", "value": "user"}]}             | ({"u": user} if user else {})
        return client.post(
            "/graphql",
            headers=auth([tenant]),
            data={"operations": json.dumps({"query": query, "variables": variables}),
                  "map": json.dumps({"0": ["variables.file"]})},
            files={"0": ("x.pdf", PDF, "application/pdf")},
        )

    for user, expected in ((user_id, user_id), (None, None)):
        r = add(user)
        assert r.json() == {"data": {"addFile": {"__typename": "AddFile", "userId": expected, "attributes": stored}}}
