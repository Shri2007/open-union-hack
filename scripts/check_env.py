"""Report which environment variables are set. Prints only the NAME and "set" or "MISSING", never a value.

Run from the repo root:  python scripts/check_env.py
Exit code 1 if any required variable is missing.
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: E402,F401  (importing it loads .env without overriding real env vars)

# (name, required). Optional ones let their integration be skipped.
VARS = [
    ("SINGLESTORE_URL", True),
    ("ARCEE_API_KEY", True),
    ("ARCEE_MODEL_SMALL", True),
    ("ARCEE_MODEL_LARGE", True),
    ("TYPESAFE_API_KEY", True),
    ("SENSO_API_KEY", True),
    ("SENSO_BASE_URL", False),  # defaults to https://apiv2.senso.ai/api/v1
    ("PERSONA_API_KEY", True),
    ("PERSONA_TEMPLATE_ID", True),
    ("ANTHROPIC_API_KEY", True),
    ("STATSIG_SERVER_KEY", False),
    ("AMPLITUDE_API_KEY", False),
    ("AIRBYTE_CLOUD_CLIENT_ID", False),
    ("AIRBYTE_CLOUD_CLIENT_SECRET", False),
    ("AIRBYTE_CLOUD_WORKSPACE_ID", False),
    ("FIREDRILL_API_KEY", False),  # may be empty: that integration is skipped
]


def main() -> int:
    missing_required = []
    for name, required in VARS:
        is_set = bool(os.environ.get(name, "").strip())
        print(f"{name:32s} {'set' if is_set else 'MISSING'}{'' if required else '  (optional)'}")
        if required and not is_set:
            missing_required.append(name)
    if missing_required:
        print("\nMissing required: " + ", ".join(missing_required))
        return 1
    print("\nAll required variables are set.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
