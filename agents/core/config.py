"""Vertex AI + model configuration.

All agents use Gemini 2.5 Flash via Vertex AI. This module is the single
point of truth for model initialization. Nothing else should import
pydantic_ai.models.google directly.
"""

import os

from pydantic_ai.models.google import GoogleModel

GCP_PROJECT = os.environ.get("GCP_PROJECT", "")
GCP_LOCATION = os.environ.get("GCP_LOCATION", "us-central1")
MODEL_NAME = os.environ.get("OUROBOROS_MODEL", "gemini-2.5-flash")


def get_model() -> GoogleModel:
    """Return the configured Vertex AI model instance."""
    if not GCP_PROJECT:
        raise RuntimeError(
            "GCP_PROJECT environment variable is required. Set it to your Google Cloud project ID."
        )
    return GoogleModel(
        MODEL_NAME,
        provider="google-vertex",
    )
