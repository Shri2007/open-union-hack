"""Settings from the environment. Missing optional keys never crash startup."""
import os
from pathlib import Path

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _load_dotenv() -> None:
    # uvicorn doesn't read .env, so load it ourselves without overriding real env vars.
    if not _ENV_FILE.exists():
        return
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


def env(name: str) -> str:
    return os.environ.get(name, "").strip()


SINGLESTORE_URL = env("SINGLESTORE_URL")
ARCEE_API_KEY = env("ARCEE_API_KEY")
ARCEE_MODEL_SMALL = env("ARCEE_MODEL_SMALL")
ARCEE_MODEL_LARGE = env("ARCEE_MODEL_LARGE")
TYPESAFE_API_KEY = env("TYPESAFE_API_KEY")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY")
SENSO_API_KEY = env("SENSO_API_KEY")
SENSO_BASE_URL = env("SENSO_BASE_URL") or "https://apiv2.senso.ai/api/v1"
PERSONA_API_KEY = env("PERSONA_API_KEY")
PERSONA_TEMPLATE_ID = env("PERSONA_TEMPLATE_ID")

INTEGRATIONS = {
    "singlestore": bool(SINGLESTORE_URL),
    "arcee": bool(ARCEE_API_KEY),
    "anthropic": bool(ANTHROPIC_API_KEY),
    "typesafe": bool(TYPESAFE_API_KEY),
    "senso": bool(SENSO_API_KEY),
    "persona": bool(PERSONA_API_KEY and PERSONA_TEMPLATE_ID),
}
