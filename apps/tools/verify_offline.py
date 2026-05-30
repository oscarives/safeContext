#!/usr/bin/env python3
"""verify_offline.py — Verificador offline de evidencia SafeContext (F8-4, ADR-015).

Comprueba, **sin red, sin Vault y sin confiar en SafeContext**, que una evidencia
firmada es auténtica: recomputa el hash canónico de la operación a partir de los
campos mostrados y verifica la firma asimétrica ECDSA-P256 con la clave pública
embebida en el propio export. Es la herramienta que se entrega a un auditor o
tribunal.

Sólo depende de la librería estándar + ``cryptography``.

Uso:
    python verify_offline.py audit_export.json
    python verify_offline.py anchor.json
    cat export.json | python verify_offline.py -

Entradas aceptadas:
  - Audit export  (GET /v1/audit/{trace_id}) → verifica digital_signature sobre el
    operation_hash recomputado desde el campo ``operation``.
  - Chain anchor  (POST /v1/audit/chain/anchor) → verifica ``signature`` sobre
    ``chain_head_hash``.

Código de salida: 0 si la evidencia verifica, 1 si falla o falta material.
"""
from __future__ import annotations

import base64
import hashlib
import json
import sys

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.exceptions import InvalidSignature
except ImportError:  # pragma: no cover - mensaje de ayuda
    sys.stderr.write(
        "Falta la dependencia 'cryptography'. Instálala con: pip install cryptography\n"
    )
    raise SystemExit(2)


# ── Primitivos canónicos (réplica exacta de db/evidence.py) ──────────────────


def compute_operation_hash(operation: dict) -> str:
    """Recomputa el hash de la operación EXACTAMENTE como el servidor al firmar.

    Debe coincidir byte a byte con ``db.evidence.compute_operation_hash``: mismos
    campos, ``json.dumps(sort_keys=True)`` y SHA-256 hex.
    """
    content = json.dumps(
        {
            "id": str(operation["id"]),
            "trace_id": str(operation["trace_id"]),
            "actor_id": str(operation["actor_id"]),
            "artifact_digest": operation["artifact_digest"],
            "status": operation["status"],
            "created_at": operation["created_at"] or "",
        },
        sort_keys=True,
    )
    return hashlib.sha256(content.encode()).hexdigest()


def _strip_vault_prefix(signature: str) -> str:
    """'vault:vN:<b64>' → '<b64>'. Acepta también una firma base64 desnuda."""
    if signature.startswith("vault:"):
        parts = signature.split(":", 2)
        if len(parts) == 3:
            return parts[2]
    return signature


def verify_ecdsa(public_key_pem: str, message_hex: str, signature: str) -> bool:
    """Verifica firma ECDSA-P256 (DER) sobre ``bytes.fromhex(message_hex)``.

    Vault Transit firma con hash_algorithm=sha2-256 y sin ``prehashed``: hashea
    el input con SHA-256 antes de firmar. Por eso verificamos con ECDSA(SHA256)
    sobre el mensaje crudo (el digest de 32 bytes), reproduciendo ese hashing.
    """
    pub = serialization.load_pem_public_key(public_key_pem.encode())
    if not isinstance(pub, ec.EllipticCurvePublicKey):
        raise ValueError("La clave pública no es de curva elíptica (se esperaba ECDSA-P256)")
    sig_der = base64.b64decode(_strip_vault_prefix(signature))
    message = bytes.fromhex(message_hex)
    try:
        pub.verify(sig_der, message, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


# ── Verificadores de alto nivel ──────────────────────────────────────────────


def verify_export(export: dict) -> tuple[bool, list[str]]:
    """Verifica un audit export. Devuelve (ok, líneas de reporte)."""
    notes: list[str] = []
    op = export.get("operation")
    sig = export.get("digital_signature")
    pem = export.get("verification_public_key_pem")

    if not op:
        return False, ["✗ falta el campo 'operation'"]
    if not sig:
        return False, ["✗ no hay digital_signature (evidencia sin firma asimétrica)"]
    if not pem:
        return False, [
            "✗ no hay verification_public_key_pem embebida — no verificable offline.",
            "  (export tomado sin clave archivada; re-exportar con la clave pública)",
        ]

    op_hash = compute_operation_hash(op)
    notes.append(f"• operation_hash recomputado: {op_hash}")
    notes.append(
        f"• firma {'write-time' if export.get('signature_at_write_time') else 'read-time'}"
        f", key_version={export.get('signing_key_version')}"
    )

    ok = verify_ecdsa(pem, op_hash, sig)
    notes.append(
        "✓ firma ECDSA-P256 VÁLIDA sobre el operation_hash recomputado"
        if ok
        else "✗ firma ECDSA-P256 INVÁLIDA — la evidencia no corresponde a estos campos"
    )
    return ok, notes


def verify_anchor(anchor: dict) -> tuple[bool, list[str]]:
    """Verifica un chain anchor. Devuelve (ok, líneas de reporte)."""
    head = anchor.get("chain_head_hash")
    sig = anchor.get("signature")
    pem = anchor.get("signing_public_key_pem")
    notes: list[str] = []

    if not head or not sig:
        return False, ["✗ anchor incompleto (faltan chain_head_hash o signature)"]
    if not pem:
        return False, ["✗ no hay signing_public_key_pem en el anchor — no verificable offline"]

    notes.append(f"• chain_head_hash: {head}")
    notes.append(f"• key_version={anchor.get('signing_key_version')}")
    ok = verify_ecdsa(pem, head, sig)
    notes.append(
        "✓ firma del anchor VÁLIDA sobre chain_head_hash"
        if ok
        else "✗ firma del anchor INVÁLIDA"
    )
    return ok, notes


def verify_document(doc: dict) -> tuple[bool, list[str]]:
    """Despacha según el tipo de evidencia (export vs anchor)."""
    if "chain_head_hash" in doc and "signature" in doc:
        return verify_anchor(doc)
    return verify_export(doc)


def main(argv: list[str]) -> int:
    # Robustez de salida: consolas no-UTF8 (p.ej. Windows cp1252) no pueden
    # imprimir ✓/✗ — forzar UTF-8 con reemplazo en vez de reventar.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            pass
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return 2
    raw = sys.stdin.read() if argv[1] == "-" else open(argv[1], encoding="utf-8").read()
    try:
        doc = json.loads(raw)
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"JSON inválido: {exc}\n")
        return 2

    ok, notes = verify_document(doc)
    print("\n".join(notes))
    print("\nRESULTADO:", "EVIDENCIA VÁLIDA ✓" if ok else "EVIDENCIA NO VÁLIDA ✗")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
