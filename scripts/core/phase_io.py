from pathlib import Path

import yaml


def load_variant_params(get_variant_dir_fn, phase: str, variant: str, phase_tag: str):
    path = get_variant_dir_fn(phase, variant) / "params.yaml"
    if not path.exists():
        raise RuntimeError(f"[{phase_tag}] params.yaml no encontrado: {path}")
    return yaml.safe_load(path.read_text())


def load_phase_outputs(project_root: Path, phase: str, variant: str, phase_tag: str):
    base = project_root / "executions" / phase / variant
    path = base / "outputs.yaml"
    if not path.exists():
        raise RuntimeError(f"[{phase_tag}] outputs.yaml no encontrado: {path}")
    return yaml.safe_load(path.read_text()), base


def load_yaml_file(path: Path, what: str, phase_tag: str):
    if not path.exists():
        raise RuntimeError(f"[{phase_tag}] {what} no encontrado: {path}")
    return yaml.safe_load(path.read_text())


def resolve_artifact_path(parent_dir: Path, outputs: dict, keys: list[str], phase_tag: str) -> Path:
    cursor = outputs.get("artifacts", {})
    traversed = ["artifacts"]

    for key in keys:
        traversed.append(key)
        if not isinstance(cursor, dict) or key not in cursor:
            joined = ".".join(traversed)
            raise RuntimeError(f"[{phase_tag}] Falta artifact requerido en outputs: {joined}")
        cursor = cursor[key]

    if not isinstance(cursor, dict) or "path" not in cursor:
        joined = ".".join(traversed + ["path"])
        raise RuntimeError(f"[{phase_tag}] Falta artifact path en outputs: {joined}")

    return parent_dir / str(cursor["path"])