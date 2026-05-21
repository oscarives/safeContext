#!/usr/bin/env python3
"""
bulk-create-users.py — Crea usuarios en Keycloak desde un archivo CSV.

Uso:
    python bulk-create-users.py --csv usuarios.csv \
        --keycloak-url http://IP-SERVIDOR:8080 \
        --admin-user admin \
        --admin-password SECRET \
        [--realm safecontext] \
        [--dry-run]

Formato del CSV (con cabecera):
    username,email,first_name,last_name,role
    juan.perez,juan@empresa.com,Juan,Pérez,viewer
    ana.garcia,ana@empresa.com,Ana,García,reviewer
    ...

Roles válidos: viewer | reviewer | policy_editor | admin
El script asigna contraseña temporal = username + "@Sc1!" (ej. juan.perez@Sc1!)
El usuario DEBE cambiarla en el primer login.
"""

import argparse
import csv
import json
import sys
import urllib.request
import urllib.error
import urllib.parse

VALID_ROLES = {"viewer", "reviewer", "policy_editor", "admin"}


def get_admin_token(base_url: str, realm: str, user: str, password: str) -> str:
    url = f"{base_url}/realms/master/protocol/openid-connect/token"
    data = urllib.parse.urlencode({
        "client_id": "admin-cli",
        "grant_type": "password",
        "username": user,
        "password": password,
    }).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())["access_token"]


def api_request(method: str, url: str, token: str, body=None):
    data = json.dumps(body).encode() if body else None
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}") from e


def create_user(base_url: str, realm: str, token: str, row: dict, dry_run: bool) -> str:
    username = row["username"].strip()
    email = row["email"].strip()
    first_name = row["first_name"].strip()
    last_name = row["last_name"].strip()
    role = row["role"].strip().lower()

    if role not in VALID_ROLES:
        raise ValueError(f"Rol inválido '{role}'. Válidos: {VALID_ROLES}")

    temp_password = f"{username}@Sc1!"

    user_payload = {
        "username": username,
        "email": email,
        "firstName": first_name,
        "lastName": last_name,
        "enabled": True,
        "emailVerified": True,
        "credentials": [
            {"type": "password", "value": temp_password, "temporary": True}
        ],
        "requiredActions": ["UPDATE_PASSWORD"],
    }

    if dry_run:
        print(f"  [DRY-RUN] Crearía: {username} <{email}> rol={role} pass={temp_password}")
        return username

    users_url = f"{base_url}/admin/realms/{realm}/users"
    try:
        api_request("POST", users_url, token, user_payload)
    except RuntimeError as e:
        if "409" in str(e):
            print(f"  [SKIP] {username} ya existe")
            return username
        raise

    # Obtener el ID del usuario recién creado
    search_url = f"{users_url}?username={urllib.parse.quote(username)}&exact=true"
    users = api_request("GET", search_url, token)
    if not users:
        raise RuntimeError(f"No se pudo encontrar el usuario '{username}' tras crearlo")
    user_id = users[0]["id"]

    # Obtener el ID del rol
    roles_url = f"{base_url}/admin/realms/{realm}/roles/{role}"
    role_data = api_request("GET", roles_url, token)

    # Asignar el rol
    assign_url = f"{users_url}/{user_id}/role-mappings/realm"
    api_request("POST", assign_url, token, [role_data])

    print(f"  [OK] {username} <{email}> rol={role}  pass_temporal={temp_password}")
    return username


def main():
    parser = argparse.ArgumentParser(description="Bulk create Keycloak users from CSV")
    parser.add_argument("--csv", required=True, help="Ruta al archivo CSV")
    parser.add_argument("--keycloak-url", required=True, help="URL base de Keycloak (sin /auth)")
    parser.add_argument("--admin-user", required=True, help="Usuario admin de Keycloak")
    parser.add_argument("--admin-password", required=True, help="Password admin de Keycloak")
    parser.add_argument("--realm", default="safecontext", help="Nombre del realm (default: safecontext)")
    parser.add_argument("--dry-run", action="store_true", help="Simula sin crear nada")
    args = parser.parse_args()

    print(f"Conectando a Keycloak: {args.keycloak_url}")
    if args.dry_run:
        print("MODO DRY-RUN — no se creará nada\n")

    try:
        token = get_admin_token(args.keycloak_url, args.realm, args.admin_user, args.admin_password)
    except Exception as e:
        print(f"ERROR: No se pudo autenticar con Keycloak: {e}", file=sys.stderr)
        sys.exit(1)

    with open(args.csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Procesando {len(rows)} usuarios...\n")
    ok = 0
    errors = 0
    for i, row in enumerate(rows, 1):
        try:
            create_user(args.keycloak_url, args.realm, token, row, args.dry_run)
            ok += 1
        except Exception as e:
            print(f"  [ERROR] fila {i} ({row.get('username', '?')}): {e}")
            errors += 1

    print(f"\nResumen: {ok} creados, {errors} errores")
    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
