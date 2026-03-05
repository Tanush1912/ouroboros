"""Vertex AI + model configuration.

All agents use Gemini 3.0 Flash via Vertex AI. This module is the single
point of truth for model initialization. Nothing else should import vertexai directly.
"""

import os

import vertexai
from pydantic_ai.models.vertexai import VertexAIModel

GCP_PROJECT = os.environ.get("GCP_PROJECT", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL_NAME = os.environ.get("OUROBOROS_MODEL", "gemini-3.0-flash-preview")

_initialized = False


def _ensure_initialized() -> None:
    global _initialized
    if not _initialized:
        if not GCP_PROJECT:
            raise RuntimeError(
                "GCP_PROJECT environment variable is required. "
                "Set it to your Google Cloud project ID."
            )
        vertexai.init(project=GCP_PROJECT, location=GCP_LOCATION)
        _initialized = True


def get_model() -> VertexAIModel:
    """Return the configured Vertex AI model instance."""
    _ensure_initialized()
    return VertexAIModel(MODEL_NAME)


