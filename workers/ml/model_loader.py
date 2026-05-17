"""Model loader for air-gapped operation.

All models must be present at build time (in the Docker image) or
at a mounted volume path. No downloads at runtime.

Model resolution priority:
1. LOCAL_MODELS_PATH env var (volume mount for updates)
2. /models/ directory inside the image (baked-in at build time)
3. spaCy/Presidio default paths (fallback — triggers download if not present)

In air-gapped environments, only paths 1 and 2 are valid.
"""
from __future__ import annotations

import os
from pathlib import Path
import structlog

log = structlog.get_logger()

# Path where models are baked into the image
IMAGE_MODELS_PATH = Path("/models")

# Path for externally-mounted model updates (air-gapped update mechanism)
LOCAL_MODELS_PATH = Path(os.environ.get("LOCAL_MODELS_PATH", "/models/local"))

# Model names used in this project
SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_lg")
TRANSFORMERS_CACHE = Path(os.environ.get("TRANSFORMERS_CACHE", "/models/transformers"))


def get_spacy_model_path() -> str | None:
    """Return path to spaCy model if available locally."""
    # Check volume-mounted path first (for updates)
    mounted = LOCAL_MODELS_PATH / "spacy" / SPACY_MODEL
    if mounted.exists():
        log.info("model_loader.spacy_from_volume", path=str(mounted))
        return str(mounted)
    # Check image-baked path
    image_path = IMAGE_MODELS_PATH / "spacy" / SPACY_MODEL
    if image_path.exists():
        log.info("model_loader.spacy_from_image", path=str(image_path))
        return str(image_path)
    # Fallback to spaCy default (triggers download if not cached — NOT for air-gapped)
    log.warning(
        "model_loader.spacy_fallback_default",
        model=SPACY_MODEL,
        warning="This will attempt to download in non-air-gapped environments",
    )
    return None  # spacy.load(SPACY_MODEL) will use default resolution


def get_transformers_cache_dir() -> str:
    """Return the transformers cache directory (local, no downloads)."""
    # Use volume-mounted path if available
    mounted = LOCAL_MODELS_PATH / "transformers"
    if mounted.exists():
        return str(mounted)
    # Use image-baked path
    if TRANSFORMERS_CACHE.exists():
        return str(TRANSFORMERS_CACHE)
    return str(TRANSFORMERS_CACHE)


def verify_models_available() -> dict[str, bool]:
    """Verify that all required models are available locally.

    Returns a dict of {model_name: is_available}.
    Used at startup to detect misconfigured air-gapped deployments.
    """
    results: dict[str, bool] = {}

    # Check spaCy model
    spacy_path = get_spacy_model_path()
    if spacy_path:
        results[f"spacy.{SPACY_MODEL}"] = Path(spacy_path).exists()
    else:
        # Try to import and check if model is installed in Python env
        try:
            import spacy

            spacy.load(SPACY_MODEL)
            results[f"spacy.{SPACY_MODEL}"] = True
        except OSError:
            results[f"spacy.{SPACY_MODEL}"] = False
            log.error("model_loader.spacy_not_found", model=SPACY_MODEL)

    # Check Presidio (it uses spaCy internally)
    try:
        from presidio_analyzer import AnalyzerEngine

        AnalyzerEngine()
        results["presidio.analyzer"] = True
    except Exception as exc:  # noqa: BLE001
        results["presidio.analyzer"] = False
        log.error("model_loader.presidio_failed", error=str(exc))

    return results


def load_spacy_nlp():
    """Load spaCy NLP model from local path."""
    import spacy

    model_path = get_spacy_model_path()
    if model_path:
        return spacy.load(model_path)
    return spacy.load(SPACY_MODEL)
