"""Tests F8-4 — verificador offline standalone (apps/tools/verify_offline.py).

Genera una clave EC P-256 real, firma como lo hace Vault Transit (hash_algorithm
sha2-256, no prehashed ⇒ ECDSA sobre el mensaje hasheado con SHA-256) y comprueba
que el verificador acepta evidencia auténtica y rechaza evidencia manipulada,
**sin red ni Vault**.
"""
from __future__ import annotations

import base64
import importlib.util
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

# Cargar el módulo standalone por ruta (vive fuera del paquete api).
_MODULE_PATH = Path(__file__).resolve().parents[3] / "tools" / "verify_offline.py"
_spec = importlib.util.spec_from_file_location("verify_offline", _MODULE_PATH)
assert _spec and _spec.loader
verify_offline = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_offline)


def _keypair() -> tuple[ec.EllipticCurvePrivateKey, str]:
    priv = ec.generate_private_key(ec.SECP256R1())
    pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return priv, pem


def _vault_style_signature(priv: ec.EllipticCurvePrivateKey, message_hex: str) -> str:
    """Firma como Vault Transit: ECDSA(SHA256) sobre los bytes del digest, DER,
    base64, prefijo vault:v1:."""
    sig_der = priv.sign(bytes.fromhex(message_hex), ec.ECDSA(hashes.SHA256()))
    return "vault:v1:" + base64.b64encode(sig_der).decode()


_SAMPLE_OP = {
    "id": "11111111-1111-1111-1111-111111111111",
    "trace_id": "22222222-2222-2222-2222-222222222222",
    "actor_id": "33333333-3333-3333-3333-333333333333",
    "artifact_digest": "digest-xyz",
    "status": "completed",
    "created_at": "2026-05-28T00:00:00+00:00",
}


def test_verify_export_valid() -> None:
    priv, pem = _keypair()
    op_hash = verify_offline.compute_operation_hash(_SAMPLE_OP)
    export = {
        "operation": _SAMPLE_OP,
        "digital_signature": _vault_style_signature(priv, op_hash),
        "verification_public_key_pem": pem,
        "signature_at_write_time": True,
        "signing_key_version": 1,
    }
    ok, notes = verify_offline.verify_export(export)
    assert ok is True, notes


def test_verify_export_detects_tampering() -> None:
    """Si alguien altera un campo de la operación tras firmar, la firma no valida."""
    priv, pem = _keypair()
    op_hash = verify_offline.compute_operation_hash(_SAMPLE_OP)
    sig = _vault_style_signature(priv, op_hash)

    tampered_op = dict(_SAMPLE_OP)
    tampered_op["status"] = "rejected"  # cambia el contenido firmado
    export = {
        "operation": tampered_op,
        "digital_signature": sig,
        "verification_public_key_pem": pem,
    }
    ok, _ = verify_offline.verify_export(export)
    assert ok is False


def test_verify_export_wrong_key_fails() -> None:
    """Una clave pública distinta (otro firmante) no valida la firma."""
    priv, _ = _keypair()
    _, other_pem = _keypair()
    op_hash = verify_offline.compute_operation_hash(_SAMPLE_OP)
    export = {
        "operation": _SAMPLE_OP,
        "digital_signature": _vault_style_signature(priv, op_hash),
        "verification_public_key_pem": other_pem,
    }
    ok, _ = verify_offline.verify_export(export)
    assert ok is False


def test_verify_export_missing_pubkey() -> None:
    """Sin clave pública embebida no se puede verificar offline → falla explícito."""
    priv, _ = _keypair()
    op_hash = verify_offline.compute_operation_hash(_SAMPLE_OP)
    export = {
        "operation": _SAMPLE_OP,
        "digital_signature": _vault_style_signature(priv, op_hash),
    }
    ok, notes = verify_offline.verify_export(export)
    assert ok is False
    assert any("verification_public_key_pem" in n for n in notes)


def test_verify_anchor_valid() -> None:
    priv, pem = _keypair()
    head = "a" * 64
    anchor = {
        "chain_head_hash": head,
        "signature": _vault_style_signature(priv, head),
        "signing_public_key_pem": pem,
        "signing_key_version": 1,
    }
    ok, notes = verify_offline.verify_anchor(anchor)
    assert ok is True, notes


def test_verify_document_dispatch_and_hash_matches_server() -> None:
    """compute_operation_hash debe coincidir con la implementación del servidor."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # apps/api
    from db.evidence import compute_operation_hash as server_hash
    from uuid import UUID
    from datetime import datetime

    server = server_hash(
        operation_id=UUID(_SAMPLE_OP["id"]),
        trace_id=UUID(_SAMPLE_OP["trace_id"]),
        actor_id=UUID(_SAMPLE_OP["actor_id"]),
        artifact_digest=_SAMPLE_OP["artifact_digest"],
        status=_SAMPLE_OP["status"],
        created_at=datetime.fromisoformat(_SAMPLE_OP["created_at"]),
    )
    assert verify_offline.compute_operation_hash(_SAMPLE_OP) == server
