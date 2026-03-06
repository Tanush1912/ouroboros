"""Runtime harness models — app startup and HTTP probe results."""

from pydantic import BaseModel, Field


class ProbeResult(BaseModel):
    url: str = Field(description="URL that was probed")
    status_code: int | None = Field(
        default=None, description="HTTP status code, None if unreachable"
    )
    healthy: bool = Field(description="True if status_code matches expected")
    response_body: str = Field(default="", description="Response body (truncated to 500 chars)")
    latency_ms: float = Field(default=0.0, description="Request latency in milliseconds")
    error: str | None = Field(default=None, description="Error message if probe failed")


class AppStartupResult(BaseModel):
    container_name: str = Field(description="Docker container name")
    started: bool = Field(description="True if container started successfully")
    health_url: str = Field(default="", description="Health check URL used")
    health_status: ProbeResult | None = Field(
        default=None, description="Result of health endpoint probe"
    )
    startup_time_seconds: float = Field(
        default=0.0, description="Time to start and pass health check"
    )
    error: str | None = Field(default=None, description="Error message if startup failed")
