"""Give each Firedrill drill a fresh coalition without removing previous evidence."""
from pathlib import Path
import sys
from uuid import uuid4

directory = Path(__file__).resolve().parent
sys.path.insert(0, str(directory.parent))
from app.store import store

coalition = f"drill-{uuid4().hex[:24]}"
store.create_coalition("Simulated Firedrill P10 drill", coalition)
marker = directory / ".active-coalition"
pending = marker.with_suffix(".pending-coalition")
pending.write_text(coalition + "\n")
pending.replace(marker)
