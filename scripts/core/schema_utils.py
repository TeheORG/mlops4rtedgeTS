from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_PATH = PROJECT_ROOT / "scripts" / "traceability_schema.yaml"


def load_traceability_schema():
    if not SCHEMA_PATH.exists():
        raise FileNotFoundError(f"No existe el esquema: {SCHEMA_PATH}")
    return yaml.safe_load(SCHEMA_PATH.read_text())