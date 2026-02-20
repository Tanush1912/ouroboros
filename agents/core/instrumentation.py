"""Logfire instrumentation setup.

Call configure_logfire() once at application startup.
All PydanticAI agents and HTTPX calls are auto-instrumented.
"""

import os


def configure_logfire() -> None:
    """Configure Logfire for the Ouroboros agent system.

    Sets up:
    - PydanticAI auto-instrumentation (agent calls, tool calls, model spans)
    - HTTPX instrumentation (Vertex AI API calls)
    - Structured span data (Pydantic models surface directly in traces)
    """
    import logfire

    logfire.configure(
        service_name="ouroboros",
        service_version=os.environ.get("GIT_SHA", "dev"),
        environment=os.environ.get("ENV", "development"),
    )

    logfire.instrument_pydantic_ai()
    logfire.instrument_httpx()
