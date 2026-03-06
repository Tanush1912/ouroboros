"""Environment bootstrap — validate config and initialise services.

Call bootstrap() once at application startup before any workflow runs.
Lives in core layer: may import from models and core only.
"""

import os
import shutil
import subprocess
import sys

from agents.core.paths import repo_root


def _load_dotenv() -> None:
    """Load .env from repo root if it exists (no external dependency)."""
    env_file = repo_root() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


class BootstrapError(SystemExit):
    """Raised when a required precondition is missing."""

    def __init__(self, message: str) -> None:
        super().__init__(1)
        self.message = message


def _check_required_env(name: str) -> str:
    val = os.environ.get(name, "").strip()
    if not val:
        raise BootstrapError(
            f"Required environment variable {name} is not set.\n"
            f"Set it in your shell or add it to {repo_root() / '.env'}"
        )
    return val


def _check_gh_cli() -> bool:
    """Return True if gh CLI is installed and authenticated."""
    if not shutil.which("gh"):
        return False
    result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def bootstrap(*, require_gh: bool = True, quiet: bool = False) -> dict[str, str]:
    """Validate environment and initialise services.

    Args:
        require_gh: If True, fail when gh CLI is not authenticated.
        quiet: If True, suppress the startup banner.

    Returns:
        Dict with resolved config values.

    Raises:
        BootstrapError: On missing required configuration.
    """
    _load_dotenv()

    gcp_project = _check_required_env("GCP_PROJECT")
    gcp_location = os.environ.get("GCP_LOCATION", "us-central1")
    model_name = os.environ.get("OUROBOROS_MODEL", "gemini-3.0-flash-preview")
    logfire_token = os.environ.get("LOGFIRE_TOKEN", "")

    # gh CLI check
    gh_ok = _check_gh_cli()
    if require_gh and not gh_ok:
        raise BootstrapError(
            "GitHub CLI (gh) is not installed or not authenticated.\nRun: gh auth login"
        )

    # Initialise Logfire
    from agents.core.instrumentation import configure_logfire

    if logfire_token:
        configure_logfire()
        logfire_status = "enabled"
    else:
        logfire_status = "disabled (no LOGFIRE_TOKEN)"

    config = {
        "gcp_project": gcp_project,
        "gcp_location": gcp_location,
        "model": model_name,
        "logfire": logfire_status,
        "gh_cli": "ok" if gh_ok else "unavailable",
    }

    if not quiet:
        _print_banner(config)

    return config


def _print_banner(config: dict[str, str]) -> None:
    sys.stderr.write(
        f"ouroboros | project={config['gcp_project']} "
        f"model={config['model']} "
        f"logfire={config['logfire']} "
        f"gh={config['gh_cli']}\n"
    )
