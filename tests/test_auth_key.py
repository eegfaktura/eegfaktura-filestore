# JWT_KEY_FILE may hold a bare RSA public key or an X.509 certificate (the realm certificate other
# components read); both verify RS256 tokens. Any other content stops the start.

import datetime

import jwt
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

import app.auth
from app.config import settings
from tests.conftest import _private_key, make_token


def _certificate_pem() -> bytes:
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "EEGFaktura")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name)
            .public_key(_private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=1))
            .sign(_private_key, hashes.SHA256()))
    return cert.public_bytes(serialization.Encoding.PEM)


def _public_key_pem() -> bytes:
    return _private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)


def _load(tmp_path, monkeypatch, content: bytes) -> str:
    key_file = tmp_path / "key.pem"
    key_file.write_bytes(content)
    monkeypatch.setattr(settings, "JWT_PUBLIC_KEY_FILE", str(key_file))
    return app.auth._load_public_key()


@pytest.mark.parametrize("content", [_public_key_pem(), _certificate_pem()], ids=["public-key", "certificate"])
def test_key_file_verifies_rs256_tokens(tmp_path, monkeypatch, content):
    key = _load(tmp_path, monkeypatch, content)
    claims = jwt.decode(make_token(["RC100000"]), key, algorithms=["RS256"], audience="account")
    assert claims["tenant"] == ["RC100000"]


def test_key_file_with_a_non_rsa_key_stops_the_start(tmp_path, monkeypatch):
    ec_key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(RuntimeError, match="not an RSA key"):
        _load(tmp_path, monkeypatch, ec_key)


def test_key_file_without_a_key_stops_the_start(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="neither a PEM public key nor a PEM certificate"):
        _load(tmp_path, monkeypatch, b"not a key\n")
