# Security basics of the REST and GraphQL endpoints: token required, tenant isolation, fixed file
# categories, and an upload/download round trip for the own tenant.

import json
import time
import uuid

import jwt
from jwt.utils import force_bytes

import app.auth
from tests.conftest import _private_key, auth, make_token, new_tenant

PDF = b"%PDF-1.4\n% filestore test\n"


def upload(client, tenant, headers, category="contract"):
    return client.post(
        f"/filestore/upload/{category}/{tenant}/{uuid.uuid4()}",
        headers=headers,
        files={"file": ("vertrag.pdf", PDF, "application/pdf")},
    )


def gql(client, headers, query, variables=None):
    return client.post("/graphql", headers=headers, json={"query": query, "variables": variables or {}})


# --- no or invalid token -------------------------------------------------------------------------

def test_download_without_token_is_401(client):
    assert client.get(f"/filestore/{uuid.uuid4()}").status_code == 401


def test_upload_without_token_is_401(client):
    assert upload(client, new_tenant(), headers={}).status_code == 401


def test_graphql_without_token_is_401(client):
    assert gql(client, {}, "{ files(tenant: \"RC100000\") { id } }").status_code == 401


def test_token_without_exp_is_401(client):
    token = jwt.encode({"tenant": ["RC100000"], "aud": "account"}, _private_key, algorithm="RS256")
    r = client.get(f"/filestore/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_expired_token_is_401(client):
    token = make_token(["RC100000"], exp=int(time.time()) - 60)
    r = client.get(f"/filestore/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_hs256_token_signed_with_the_public_key_is_401(client, monkeypatch):
    # Algorithm confusion: an HS256 token whose HMAC secret is the RS256 public key would validate
    # if HS256 were in the accepted algorithms. PyJWT itself refuses a PEM key as an HMAC secret,
    # which would hide that; the test switches this guard off, so only the algorithms list of
    # app.auth.get_claims keeps the token out.
    monkeypatch.setattr(jwt.algorithms.HMACAlgorithm, "prepare_key", lambda self, key: force_bytes(key))
    token = jwt.encode({"tenant": ["RC100000"], "aud": "account", "exp": int(time.time()) + 300},
                       app.auth._PUBLIC_KEY, algorithm="HS256")
    r = client.get(f"/filestore/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_token_with_wrong_audience_is_401(client):
    token = make_token(["RC100000"], aud="eegfaktura-other")
    r = client.get(f"/filestore/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


# --- own tenant: upload and download -------------------------------------------------------------

def test_upload_and_download_own_tenant(client):
    tenant = new_tenant()
    r = upload(client, tenant, auth([tenant]))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["file_category"] == "contract"

    r = client.get(f"/filestore/{body['id']}", headers=auth([tenant.lower()]))  # tenant case-insensitive
    assert r.status_code == 200, r.text
    assert r.content == PDF
    assert r.headers["content-type"] == "application/pdf"


def test_tenant_in_path_case_insensitive(client):
    # the other direction of the check above: lowercase tenant in the path, uppercase in the token
    tenant = new_tenant()
    r = upload(client, tenant.lower(), auth([tenant]))
    assert r.status_code == 200, r.text


# --- other tenant --------------------------------------------------------------------------------

def test_upload_for_other_tenant_is_403(client):
    assert upload(client, new_tenant(), auth([new_tenant()])).status_code == 403


def test_download_of_other_tenants_file_is_403(client):
    owner = new_tenant()
    r = upload(client, owner, auth([owner]))
    assert r.status_code == 200, r.text

    r = client.get(f"/filestore/{r.json()['id']}", headers=auth([new_tenant()]))
    assert r.status_code == 403


def test_graphql_files_of_other_tenant_is_denied(client):
    r = gql(client, auth([new_tenant()]), "query($t: String!) { files(tenant: $t) { id } }", {"t": new_tenant()})
    assert r.status_code == 200
    assert r.json()["errors"][0]["message"] == "403: Tenant not allowed"


def test_graphql_files_lists_own_tenant(client):
    tenant = new_tenant()
    file_id = upload(client, tenant, auth([tenant]), category="invoice").json()["id"]

    r = gql(client, auth([tenant]), "query($t: String!) { files(tenant: $t) { id fileCategory } }", {"t": tenant})
    assert r.status_code == 200, r.text
    assert r.json()["data"]["files"] == [{"id": file_id, "fileCategory": "invoice"}]


def test_superuser_reaches_other_tenant(client):
    # The realm role "superuser" skips the tenant check (Claims.is_superuser, as in the backend).
    owner = new_tenant()
    file_id = upload(client, owner, auth([owner])).json()["id"]
    superuser = {"Authorization": f"Bearer {make_token([new_tenant()], realm_access={'roles': ['superuser']})}"}

    assert client.get(f"/filestore/{file_id}", headers=superuser).status_code == 200
    r = gql(client, superuser, "query($t: String!) { files(tenant: $t) { id } }", {"t": owner})
    assert r.json()["data"]["files"] == [{"id": file_id}]
    assert upload(client, owner, superuser).status_code == 200


# --- GEA: sub-community tenants (GCxxxxxx-00n) share the files of their stem (GCxxxxxx) ----------

def new_gea_stem() -> str:
    return "GC" + str(uuid.uuid4().int)[:6]


def test_gea_sub_community_token_reaches_stem_files(client):
    stem = new_gea_stem()
    r = upload(client, f"{stem}-003", auth([f"{stem}-003"]))  # stored under the stem
    assert r.status_code == 200, r.text
    file_id = r.json()["id"]

    other_sub = auth([f"{stem}-001"])
    assert client.get(f"/filestore/{file_id}", headers=other_sub).status_code == 200
    r = gql(client, other_sub, "query($t: String!) { files(tenant: $t) { id } }", {"t": stem})
    assert r.json()["data"]["files"] == [{"id": file_id}]


def test_gea_stem_token_reaches_sub_community(client):
    stem = new_gea_stem()
    r = upload(client, f"{stem}-002", auth([stem]))
    assert r.status_code == 200, r.text
    file_id = r.json()["id"]

    assert client.get(f"/filestore/{file_id}", headers=auth([stem])).status_code == 200
    r = gql(client, auth([stem]), "query($t: String!) { files(tenant: $t) { id } }", {"t": f"{stem}-002"})
    assert r.json()["data"]["files"] == [{"id": file_id}]


def test_gea_other_stem_is_403(client):
    stem = new_gea_stem()
    file_id = upload(client, stem, auth([stem])).json()["id"]
    other = auth([f"{new_gea_stem()}-001"])
    assert client.get(f"/filestore/{file_id}", headers=other).status_code == 403
    assert upload(client, f"{stem}-001", other).status_code == 403


# --- file categories: only contract and invoice --------------------------------------------------

def test_rest_upload_with_unknown_category_is_rejected(client):
    tenant = new_tenant()
    assert upload(client, tenant, auth([tenant]), category="other").status_code == 422


def test_graphql_upload_with_unknown_category_is_rejected(client):
    tenant = new_tenant()
    query = ("mutation($file: Upload!, $t: String!, $c: String!) {"
             " addFile(file: $file, name: \"x\", fileCategory: $c, tenant: $t) {"
             " __typename ... on AddFileError { message } } }")
    operations = {"query": query, "variables": {"file": None, "t": tenant, "c": "other"}}
    r = client.post(
        "/graphql",
        headers=auth([tenant]),
        data={"operations": json.dumps(operations), "map": json.dumps({"0": ["variables.file"]})},
        files={"0": ("x.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["addFile"] == {"__typename": "AddFileError", "message": "Invalid file category"}
