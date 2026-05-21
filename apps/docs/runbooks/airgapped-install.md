# Runbook: Instalación Air-Gapped

**Versión**: 1.0.0 · **Prerrequisito**: bundle SafeContext descargado

## Proceso completo sin internet

### Paso 1: Transferir bundle al host de destino

```bash
# En máquina con internet:
scp dist/safecontext-bundle-1.0.0.tar.gz operator@airgapped-host:/opt/safecontext/
```

### Paso 2: Instalar desde bundle

```bash
cd /opt/safecontext
./infra/scripts/install-bundle.sh safecontext-bundle-1.0.0.tar.gz
```

### Paso 3: Configurar entorno

```bash
cp .env.example .env
# Editar .env con valores de producción
```

### Paso 4: Levantar stack

```bash
docker compose up -d
sleep 30
curl http://localhost/health
```

### Verificación de éxito

- `GET /health` retorna `{"status": "ok"}`
- `docker compose ps` muestra todos los servicios `healthy`
- 0 requests salientes de red durante la instalación
