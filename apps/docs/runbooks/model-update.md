# Runbook: Actualización de Modelos NLP/ML (Air-Gapped)

**Versión**: 1.0.0
**Épica**: E5.3 — Modelos NLP/ML empaquetados para operación offline

## Estrategia de distribución de modelos

Los modelos spaCy, Presidio y Transformers se gestionan de dos formas:

| Mecanismo | Cuándo usar |
|---|---|
| **Baked en imagen** | Versión estable; modelos viajan con la imagen de contenedor |
| **Volumen montado** | Actualización de modelos sin rebuild de imagen; ruta `/models/local/` |

El `model_loader` (`workers/ml/model_loader.py`) resuelve rutas en este orden:

1. `LOCAL_MODELS_PATH` env var (volumen montado — para actualizaciones)
2. `/models/` dentro de la imagen (baked-in en build time)
3. Paths por defecto de spaCy/Presidio (fallback — descarga si no está disponible; **NO usar en air-gapped**)

## Actualización de modelo vía imagen (rebuild)

```bash
# Con internet (en build server):
docker build -t safecontext/safecontext-worker:NEW_VERSION workers/
docker save safecontext/safecontext-worker:NEW_VERSION -o worker-new.tar

# Transferir al entorno air-gapped
scp worker-new.tar operator@airgapped-host:/opt/safecontext/

# En entorno air-gapped:
docker load -i worker-new.tar
docker compose up -d --no-deps worker
```

## Actualización de modelo vía volumen (sin rebuild)

```bash
# Preparar bundle de modelo (con internet):
mkdir -p model-bundle/spacy
python -c "import spacy; spacy.cli.download('en_core_web_lg')"
python -c "import spacy; m=spacy.load('en_core_web_lg'); print(m.path)" | \
  xargs -I{} cp -r {} model-bundle/spacy/en_core_web_lg/
tar -czf spacy-en_core_web_lg-update.tar.gz model-bundle/

# Transferir y aplicar:
scp spacy-en_core_web_lg-update.tar.gz operator@airgapped-host:/opt/models/
tar -xzf spacy-en_core_web_lg-update.tar.gz -C /opt/models/

# Reiniciar workers para cargar nuevo modelo:
docker compose restart worker

# Verificar recall post-update:
docker compose exec worker pytest tests/ml/test_recall.py -v
```

## Variables de entorno relevantes

| Variable | Default (imagen) | Descripción |
|---|---|---|
| `LOCAL_MODELS_PATH` | `/models/local` | Volumen con modelos actualizados (mayor prioridad) |
| `TRANSFORMERS_CACHE` | `/models/transformers` | Cache de modelos HuggingFace |
| `SPACY_MODEL` | `en_core_web_lg` | Nombre del modelo spaCy a cargar |
| `TRANSFORMERS_OFFLINE` | `1` | Evita descarga de modelos HuggingFace |
| `HF_DATASETS_OFFLINE` | `1` | Evita descarga de datasets HuggingFace |

## Verificación post-actualización

```bash
docker compose exec worker python -c "
from workers.ml.model_loader import verify_models_available
results = verify_models_available()
for model, available in results.items():
    print(f'{model}: {\"OK\" if available else \"MISSING\"}')"
```

Salida esperada:

```
spacy.en_core_web_lg: OK
presidio.analyzer: OK
```

## Recall mínimo requerido

| Clase | F1 | F2 | F5 |
|---|---|---|---|
| EMAIL_ADDRESS | ≥ 0.90 | ≥ 0.95 | ≥ 0.98 |
| API_KEY | ≥ 0.90 | ≥ 0.95 | ≥ 0.98 |
| PERSON | ≥ 0.90 | ≥ 0.95 | ≥ 0.98 |

La gate **F1 (≥ 0.90)** se verifica en CI con `test_recall.py`.
La gate **F5 (≥ 0.98)** se verifica en `test_offline_models.py` con `@pytest.mark.integration`.

## Estructura de directorios de modelos

```
/models/
├── spacy/
│   └── en_core_web_lg/        # modelo baked o montado vía volumen
├── transformers/              # cache HuggingFace (baked o volumen)
└── local/                     # punto de montaje para actualizaciones de volumen
    ├── spacy/
    │   └── en_core_web_lg/    # sobreescribe imagen si existe
    └── transformers/
```

## Rollback

```bash
# Volver a la versión anterior de imagen:
docker compose down worker
docker tag safecontext/safecontext-worker:PREVIOUS_VERSION \
           safecontext/safecontext-worker:latest
docker compose up -d worker

# Si se usó volumen, eliminar el modelo problemático:
rm -rf /opt/models/local/spacy/en_core_web_lg
docker compose restart worker
```
