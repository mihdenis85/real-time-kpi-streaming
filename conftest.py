import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SERVICE_SRC_PATHS = [
    ROOT / "services" / "alerting" / "src",
    ROOT / "services" / "ingest-api" / "src",
    ROOT / "services" / "stream-processor" / "src",
    ROOT / "services" / "simulator" / "src",
]

for src_path in SERVICE_SRC_PATHS:
    path_str = str(src_path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)
