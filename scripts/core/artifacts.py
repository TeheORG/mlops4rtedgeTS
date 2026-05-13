import hashlib
from pathlib import Path
import yaml
import json


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_params(phase: str, variant: str) -> dict:
    variant_dir = PROJECT_ROOT / "executions" / phase / variant
    params_path = variant_dir / "params.yaml"

    if not params_path.exists():
        raise RuntimeError(
            f"No existe params.yaml para {phase}:{variant}"
        )

    data = yaml.safe_load(params_path.read_text())

    if not isinstance(data, dict):
        raise RuntimeError("params.yaml inválido")

    return data


def get_variant_dir(phase: str, variant: str) -> Path:
    variant_dir = PROJECT_ROOT / "executions" / phase / variant

    if not variant_dir.exists():
        raise RuntimeError(f"No existe la variante {phase}:{variant}")

    return variant_dir

# ============================================================
# HASH
# ============================================================

def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


# ============================================================
# OUTPUTS
# ============================================================

def save_outputs_yaml(variant_dir: Path, content: dict):
    outputs_path = variant_dir / "outputs.yaml"
    yaml.safe_dump(content, outputs_path.open("w"), sort_keys=False)
    return outputs_path

def save_json(path: Path, data: dict, indent: int = 2):
    """
    Guarda JSON de forma consistente en todo el proyecto.
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=indent)


def load_json(path: Path):
    """
    Carga JSON de forma consistente.
    """
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

