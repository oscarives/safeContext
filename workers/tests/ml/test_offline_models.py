"""Tests E5.3 — Offline model availability and air-gapped operation.

Criterios:
- Modelos disponibles sin acceso a internet
- model_loader resuelve rutas correctamente
- verify_models_available retorna estado correcto
- PresidioDetector inicializa desde paths locales
"""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest


class TestModelLoader:
    def test_verify_models_returns_dict(self):
        """verify_models_available returns dict with model names as keys."""
        from workers.ml.model_loader import verify_models_available

        result = verify_models_available()
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_verify_models_keys_are_strings(self):
        """All keys in verify_models_available result are strings."""
        from workers.ml.model_loader import verify_models_available

        result = verify_models_available()
        for key in result:
            assert isinstance(key, str), f"Key {key!r} is not a string"

    def test_verify_models_values_are_bools(self):
        """All values in verify_models_available result are booleans."""
        from workers.ml.model_loader import verify_models_available

        result = verify_models_available()
        for key, val in result.items():
            assert isinstance(val, bool), f"Value for {key!r} is not a bool"

    def test_get_spacy_model_path_prefers_volume(self, tmp_path):
        """model_loader prefers volume-mounted path over image path."""
        spacy_dir = tmp_path / "spacy" / "en_core_web_lg"
        spacy_dir.mkdir(parents=True)

        with patch.dict(os.environ, {"LOCAL_MODELS_PATH": str(tmp_path)}):
            import importlib

            import workers.ml.model_loader as ml

            importlib.reload(ml)

            path = ml.get_spacy_model_path()
            assert path is not None
            assert str(tmp_path) in path

    def test_get_spacy_model_path_falls_back_to_image(self, tmp_path):
        """Falls back to /models path if volume not found."""
        image_models = tmp_path / "spacy" / "en_core_web_lg"
        image_models.mkdir(parents=True)

        with patch("workers.ml.model_loader.IMAGE_MODELS_PATH", tmp_path):
            with patch(
                "workers.ml.model_loader.LOCAL_MODELS_PATH", tmp_path / "nonexistent"
            ):
                import workers.ml.model_loader as ml

                path = ml.get_spacy_model_path()
                # Falls back to image path
                assert path is not None
                assert str(tmp_path) in path

    def test_get_spacy_model_path_returns_none_when_not_found(self, tmp_path):
        """Returns None (triggering spaCy default resolution) when no local path exists."""
        with patch("workers.ml.model_loader.IMAGE_MODELS_PATH", tmp_path / "nonexistent"):
            with patch(
                "workers.ml.model_loader.LOCAL_MODELS_PATH", tmp_path / "also_nonexistent"
            ):
                import workers.ml.model_loader as ml

                path = ml.get_spacy_model_path()
                assert path is None

    def test_get_transformers_cache_returns_path(self):
        """get_transformers_cache_dir always returns a path string."""
        from workers.ml.model_loader import get_transformers_cache_dir

        result = get_transformers_cache_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_get_transformers_cache_prefers_volume(self, tmp_path):
        """get_transformers_cache_dir prefers volume-mounted transformers path."""
        mounted_transformers = tmp_path / "transformers"
        mounted_transformers.mkdir(parents=True)

        with patch("workers.ml.model_loader.LOCAL_MODELS_PATH", tmp_path):
            import workers.ml.model_loader as ml

            result = ml.get_transformers_cache_dir()
            assert str(tmp_path) in result

    def test_image_models_path_constant(self):
        """IMAGE_MODELS_PATH is set to /models (the baked-in path)."""
        from workers.ml.model_loader import IMAGE_MODELS_PATH

        assert str(IMAGE_MODELS_PATH) == "/models"

    def test_spacy_model_env_override(self, tmp_path):
        """SPACY_MODEL env var overrides the default model name."""
        with patch.dict(os.environ, {"SPACY_MODEL": "en_core_web_sm"}):
            import importlib

            import workers.ml.model_loader as ml

            importlib.reload(ml)
            assert ml.SPACY_MODEL == "en_core_web_sm"

    def test_transformers_cache_env_override(self, tmp_path):
        """TRANSFORMERS_CACHE env var overrides the default cache path."""
        custom_path = str(tmp_path / "custom_transformers")
        with patch.dict(os.environ, {"TRANSFORMERS_CACHE": custom_path}):
            import importlib

            import workers.ml.model_loader as ml

            importlib.reload(ml)
            assert str(ml.TRANSFORMERS_CACHE) == custom_path


class TestOfflineOperation:
    """Tests verifying the detector can operate without internet access."""

    def test_verify_models_available_has_spacy_key(self):
        """verify_models_available always includes a spacy model key."""
        from workers.ml.model_loader import SPACY_MODEL, verify_models_available

        result = verify_models_available()
        assert f"spacy.{SPACY_MODEL}" in result

    def test_verify_models_available_has_presidio_key(self):
        """verify_models_available always includes the presidio.analyzer key."""
        from workers.ml.model_loader import verify_models_available

        result = verify_models_available()
        assert "presidio.analyzer" in result

    def test_model_loader_does_not_call_requests_on_import(self):
        """Importing model_loader does not trigger any HTTP requests."""
        import importlib
        import sys

        # Remove cached module to force fresh import
        for mod in list(sys.modules.keys()):
            if "model_loader" in mod:
                del sys.modules[mod]

        # Block socket connections during import
        import socket
        original_getaddrinfo = socket.getaddrinfo

        def no_network(*args, **kwargs):
            raise ConnectionError("Network access forbidden during model_loader import")

        socket.getaddrinfo = no_network
        try:
            import workers.ml.model_loader  # noqa: F401 — import side-effect test
        finally:
            socket.getaddrinfo = original_getaddrinfo

    @pytest.mark.integration
    def test_presidio_detector_initializes(self):
        """PresidioDetector initializes without internet (models pre-loaded)."""
        from workers.ml.presidio_detector import PresidioDetector

        detector = PresidioDetector()
        assert detector is not None

    @pytest.mark.integration
    def test_presidio_detector_has_engine(self):
        """PresidioDetector._get_analyzer() returns a valid AnalyzerEngine."""
        from presidio_analyzer import AnalyzerEngine

        from workers.ml.presidio_detector import PresidioDetector

        detector = PresidioDetector()
        engine = detector._get_analyzer()
        assert isinstance(engine, AnalyzerEngine)

    @pytest.mark.integration
    def test_recall_threshold_f1(self):
        """Recall >= 0.90 for critical classes with offline models (F1 gate)."""
        from workers.tests.ml.test_recall import ENTITY_CLASSES, evaluate_recall

        for entity_class in ENTITY_CLASSES:
            result = evaluate_recall(entity_class)
            assert result.recall >= 0.90, (
                f"{entity_class} recall {result.recall:.2f} below 0.90 "
                f"(TP={result.tp}, FN={result.fn})"
            )

    @pytest.mark.integration
    def test_recall_threshold_f5(self):
        """Recall >= 0.98 for critical classes with offline models (F5 gate).

        Note: Requires production corpus with >=50 samples per class and the
        full en_core_web_lg model baked into the image.
        """
        import json
        from pathlib import Path

        from workers.tests.ml.test_recall import (
            ENTITY_CLASSES,
            _load_corpus,
            _predictions_hit,
            Annotation,
        )
        from workers.ml.presidio_detector import PresidioDetector
        import asyncio

        corpus = _load_corpus()
        detector = PresidioDetector()
        policy = {"score_threshold": 0.3}

        for entity_class in ENTITY_CLASSES:
            tp = 0
            fn = 0
            for sample in corpus:
                text: str = sample["text"]
                gold_annotations = [
                    Annotation(
                        entity_type=ann["entity_type"],
                        span_start=ann["span_start"],
                        span_end=ann["span_end"],
                    )
                    for ann in sample.get("expected", [])
                    if ann["entity_type"] == entity_class
                ]
                if not gold_annotations:
                    continue
                predictions = asyncio.run(detector.detect(text, policy))
                for gold in gold_annotations:
                    if _predictions_hit(predictions, gold):
                        tp += 1
                    else:
                        fn += 1

            total = tp + fn
            recall = tp / total if total > 0 else 0.0
            assert recall >= 0.98, (
                f"{entity_class} F5 recall {recall:.2f} below 0.98 "
                f"(TP={tp}, FN={fn}) — check en_core_web_lg model is fully baked into image"
            )
