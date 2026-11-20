"""End-to-end proof that Cognee memory works (SIMULATED vendor). Throwaway data, dataset "open-union-demo".

Needs COGNEE_MEMORY=1 plus Cognee LLM/embedding env vars (see docs/ or the PR description).
Run: COGNEE_MEMORY=1 python scripts/cognee_demo.py
"""
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import memory  # noqa: E402

logging.basicConfig(level=logging.INFO)
NEED = "phone plan under $60, Bay Area"
SIMILAR = "cheap cell phone plan, San Francisco Bay Area"


def main() -> int:
    if not memory.enabled():
        print("Set COGNEE_MEMORY=1")
        return 2
    print(f"[sim] before: recall({NEED!r}) ->", memory.recall_walkout(NEED))
    print("[sim] remembering walkout at 6000 cents ...")
    ok = memory.remember_walkout(NEED, 6000)
    print("remember ok:", ok)
    for need in (NEED, SIMILAR):
        got = memory.recall_walkout(need)
        print(f"recall({need!r}) ->", got)
        if got:
            print(f"Northline remembers (simulated): {got['text']}")
    return 0 if ok and memory.recall_walkout(NEED) else 1


if __name__ == "__main__":
    sys.exit(main())
