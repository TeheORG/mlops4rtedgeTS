import json
import subprocess
import argparse
import sys
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any
import yaml
from scripts.core.schema_utils import load_traceability_schema as _load_traceability_schema

import hashlib


# ============================================================
# RUTAS DEL PROYECTO
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXECUTIONS_DIR = PROJECT_ROOT / "executions"
PIPELINE_REF_PATH = PROJECT_ROOT / ".mlops4ofp" / "pipeline_ref.yaml"
VARIANT_ID_REGEX = re.compile(r"^v(?P<phase>\d)_(?P<seq>\d{4})$")


# ============================================================
# UTILIDADES GIT
# ============================================================

def current_git_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return "unknown"


def git_info() -> Dict[str, Any]:
    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            text=True
        ).strip()
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            text=True
        ).strip()
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            text=True
        ).strip()

        return {
            "commit": commit,
            "branch": branch,
            "status_clean": (status == "")
        }
    except Exception:
        return {
            "commit": "unknown",
            "branch": "unknown",
            "status_clean": False
        }


# ============================================================
# PIPELINE REF
# ============================================================

def load_pipeline_ref() -> Dict[str, Any]:
    if not PIPELINE_REF_PATH.exists():
        return {
            "pipeline_repo": "unknown",
            "pipeline_commit": "unknown"
        }
    try:
        return yaml.safe_load(PIPELINE_REF_PATH.read_text())
    except Exception:
        return {
            "pipeline_repo": "unknown",
            "pipeline_commit": "unknown"
        }


def load_traceability_schema():
    try:
        return _load_traceability_schema()
    except FileNotFoundError:
        raise RuntimeError("No existe traceability_schema.yaml")


# ============================================================
# VALIDACIÓN OUTPUTS
# ============================================================

def validate_outputs(phase: str, outputs: dict):

    schema = load_traceability_schema()

    if "phases" not in schema or phase not in schema["phases"]:
        raise RuntimeError(f"No hay definición de fase {phase} en schema")

    phase_schema = schema["phases"][phase]
    outputs_schema = phase_schema.get("outputs", {})

    # --------------------------------------------------------
    # ARTIFACTS
    # --------------------------------------------------------

    artifacts_schema = outputs_schema.get("artifacts", {})
    artifacts = outputs.get("artifacts", {})

    for key, rule in artifacts_schema.items():

        if rule.get("required", False) and key not in artifacts:
            raise RuntimeError(f"Falta artifact requerido: {key}")

        if key in artifacts:
            path = artifacts[key].get("path")
            if not path:
                raise RuntimeError(f"Artifact {key} sin path")

            ext = rule.get("extension")
            if ext and not path.endswith(f".{ext}"):
                raise RuntimeError(
                    f"Artifact {key} debe tener extensión .{ext}"
                )

    # --------------------------------------------------------
    # EXPORTS
    # --------------------------------------------------------

    exports_schema = outputs_schema.get("exports", {})
    exports = outputs.get("exports", {})

    for key, rule in exports_schema.items():

        if rule.get("required", False) and key not in exports:
            raise RuntimeError(f"Falta export requerido: {key}")

        if key in exports:
            value = exports[key]
            _validate_basic_type(value, rule, f"export {key}")

    # --------------------------------------------------------
    # METRICS
    # --------------------------------------------------------

    metrics_schema = outputs_schema.get("metrics", {})
    metrics = outputs.get("metrics", {})

    for key, rule in metrics_schema.items():

        if rule.get("required", False) and key not in metrics:
            raise RuntimeError(f"Falta metric requerido: {key}")

        if key in metrics:
            value = metrics[key]
            _validate_basic_type(value, rule, f"metric {key}")

    print("[OK] Outputs validados contra schema")


# ============================================================
# VALIDACIÓN TIPOS BÁSICOS
# ============================================================

def _validate_basic_type(value, rule, context):

    if value is None:
        if rule.get("nullable", False):
            return
        raise RuntimeError(f"{context} no puede ser null")

    expected = rule.get("type")

    if expected == "integer" and not isinstance(value, int):
        raise RuntimeError(f"{context} debe ser integer")

    if expected == "float" and not isinstance(value, float):
        raise RuntimeError(f"{context} debe ser float")

    if expected == "string" and not isinstance(value, str):
        raise RuntimeError(f"{context} debe ser string")

    if expected == "boolean" and not isinstance(value, bool):
        raise RuntimeError(f"{context} debe ser boolean")

    if expected == "list" and not isinstance(value, list):
        raise RuntimeError(f"{context} debe ser list")

    if expected == "dict" and not isinstance(value, dict):
        raise RuntimeError(f"{context} debe ser dict")

# ============================================================
# CARGA DE VARIANTES
# ============================================================

def _extract_phase_code(phase: str) -> str | None:
    m = re.match(r"^f(\d{2})(?:_|$)", phase)
    return str(int(m.group(1))) if m else None


def _is_variant_id_for_phase(variant: str, phase: str | None = None) -> bool:
    m = VARIANT_ID_REGEX.fullmatch(variant)
    if not m:
        return False
    if not phase:
        return True
    phase_code = _extract_phase_code(phase)
    if not phase_code:
        return True
    return m.group("phase") == phase_code


def _iter_variant_dirs_for_phase(phase: str):
    phase_dir = EXECUTIONS_DIR / phase
    if not phase_dir.exists() or not phase_dir.is_dir():
        return

    for child in sorted(phase_dir.iterdir()):
        if child.is_dir() and _is_variant_id_for_phase(child.name, phase):
            yield child.name, child


def _load_variant_metadata(variant_dir: Path) -> Dict[str, Any]:
    meta_path = variant_dir / "metadata.yaml"
    if not meta_path.exists():
        return {}
    data = yaml.safe_load(meta_path.read_text())
    return data if isinstance(data, dict) else {}

def load_variants_for_phase(phase: str) -> Dict[str, Any]:
    data: Dict[str, Any] = {"variants": {}}
    for variant_name, variant_dir in _iter_variant_dirs_for_phase(phase):
        meta = _load_variant_metadata(variant_dir)
        if "params_path" not in meta:
            meta["params_path"] = str((variant_dir / "params.yaml").relative_to(PROJECT_ROOT))
        data["variants"][variant_name] = meta
    return data


def load_all_variants() -> Dict[str, Dict[str, Any]]:
    result = {}

    if not EXECUTIONS_DIR.exists():
        return result

    for ph in EXECUTIONS_DIR.iterdir():
        if not ph.is_dir():
            continue
        phase_name = ph.name
        phase_variants: Dict[str, Any] = {}
        for variant_name, variant_dir in _iter_variant_dirs_for_phase(phase_name):
            meta = _load_variant_metadata(variant_dir)
            if "params_path" not in meta:
                meta["params_path"] = str((variant_dir / "params.yaml").relative_to(PROJECT_ROOT))
            phase_variants[variant_name] = meta
        if phase_variants:
            result[phase_name] = phase_variants

    return result


# ============================================================
# VALIDACIÓN DE EXISTENCIA
# ============================================================

def validate_variant_exists(phase: str, variant: str):
    variant_dir = EXECUTIONS_DIR / phase / variant
    if not variant_dir.exists() or not variant_dir.is_dir() or not _is_variant_id_for_phase(variant, phase):
        raise ValueError(
            f"La variante {variant} no existe en la fase {phase}.\n"
            f"Ruta esperada: executions/{phase}/{variant}"
        )
    return True


# ============================================================
# RELACIONES PADRE-HIJO
# ============================================================

def find_children(phase: str, variant: str) -> List[str]:
    children = []

    for phase_dir in EXECUTIONS_DIR.iterdir():
        if not phase_dir.is_dir():
            continue
        child_phase = phase_dir.name
        for child_variant, child_dir in _iter_variant_dirs_for_phase(child_phase):
            params_path = child_dir / "params.yaml"
            if not params_path.exists():
                continue

            params_data = yaml.safe_load(params_path.read_text()) or {}
            candidate_parents: list[str] = []

            direct_parent = params_data.get("parent")
            if isinstance(direct_parent, str):
                candidate_parents.append(direct_parent)

            top_level_parents = params_data.get("parents")
            if isinstance(top_level_parents, list):
                candidate_parents.extend([str(p) for p in top_level_parents if p is not None])

            parameters = params_data.get("parameters")
            if isinstance(parameters, dict):
                nested_parents = parameters.get("parent_variant") or parameters.get("parents")
                if isinstance(nested_parents, list):
                    candidate_parents.extend([str(p) for p in nested_parents if p is not None])

            if variant in candidate_parents:
                children.append(f"{child_phase}:{child_variant}")

    return children


def can_delete_variant(phase: str, variant: str):
    validate_variant_exists(phase, variant)
    children = find_children(phase, variant)

    if children:
        msg = (
            f"[FAIL] La variante {phase}:{variant} tiene variantes hijas y NO puede borrarse.\n"
            f"Hijos:\n" + "\n".join(f"  - {c}" for c in children)
        )
        raise RuntimeError(msg)

    print(f"[OK] La variante {phase}:{variant} no tiene hijos y puede borrarse.")


# ============================================================
# ESCRITURA DE METADATA (AUTOCONTENIDO)
# ============================================================

def write_metadata(
    stage: str,
    variant: str,
    parent_variant: str | None,
    inputs: List[str],
    outputs: List[str],
    params: Dict[str, Any],
    metadata_path: str,
) -> None:

    metadata_path = Path(metadata_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)

    pipeline_ref = load_pipeline_ref()

    data = {
        "stage": stage,
        "variant": variant,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "inputs": inputs,
        "outputs": outputs,
        "params": params,
        "git": git_info(),
        "pipeline": pipeline_ref   # ← NUEVO BLOQUE AUTOCONTENIDO
    }

    if parent_variant is not None:
        data["parent_variant"] = parent_variant

    metadata_path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# ============================================================
# VALIDACIÓN DE METADATA
# ============================================================

def load_schema() -> Dict[str, Any]:
    return load_traceability_schema()


def validate_metadata(metadata: Dict[str, Any], schema: Dict[str, Any]) -> List[str]:
    errors = []
    fields = schema.get("fields", {})

    for field_name, rules in fields.items():
        if rules.get("required") and field_name not in metadata:
            errors.append(f"Falta el campo obligatorio '{field_name}'.")

    for field_name, rules in fields.items():
        if field_name not in metadata:
            continue

        expected = rules.get("type")
        val = metadata[field_name]

        if expected == "string" and not isinstance(val, str):
            errors.append(f"'{field_name}' debe ser string.")
        if expected == "list" and not isinstance(val, list):
            errors.append(f"'{field_name}' debe ser lista.")
        if expected == "dict" and not isinstance(val, dict):
            errors.append(f"'{field_name}' debe ser dict.")

    if "parent_variant" in metadata and "parent_variants" in metadata:
        errors.append(
            "No se permite definir simultáneamente "
            "'parent_variant' y 'parent_variants'."
        )
    return errors


def validate_metadata_file(metadata_path: str) -> List[str]:
    metadata = json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    schema = load_schema()
    return validate_metadata(metadata, schema)


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Herramientas de trazabilidad — MLOps4OFP-FGCS"
    )
    subparsers = parser.add_subparsers(dest="command")

    p1 = subparsers.add_parser("can-delete")
    p1.add_argument("--phase", required=True)
    p1.add_argument("--variant", required=True)

    p2 = subparsers.add_parser("validate-variant")
    p2.add_argument("--phase", required=True)
    p2.add_argument("--variant", required=True)

    args = parser.parse_args()

    try:
        if args.command == "can-delete":
            can_delete_variant(args.phase, args.variant)
        elif args.command == "validate-variant":
            # 1. existencia
            validate_variant_exists(args.phase, args.variant)
            from pathlib import Path
            import yaml
            params_path = Path("executions") / args.phase / args.variant / "params.yaml"
            if not params_path.exists():
                raise RuntimeError(f"Missing params.yaml for {args.phase}:{args.variant}")
            params = yaml.safe_load(params_path.read_text())
            audit_parents(params)
            audit_code()
            print(f"[OK] Variant {args.phase}:{args.variant} validated (audit OK)")
        else:
            parser.print_help()
            sys.exit(1)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

# ============================
# AUDIT VALIDATION
# ============================


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def _file_mtime(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def _git_diff(path: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "diff", "--", str(path)],
            text=True
        )
    except Exception:
        return "<diff not available>"


def find_parent_phase(parent_variant: str) -> str:
    """Busca en todas las fases la variante padre y devuelve la fase donde se encuentra."""
    executions_dir = Path("executions")
    for phase_dir in executions_dir.iterdir():
        if not phase_dir.is_dir():
            continue
        params_path = phase_dir / parent_variant / "params.yaml"
        if params_path.exists():
            return phase_dir.name
    raise RuntimeError(f"No se encontró la fase para el padre {parent_variant}")


def audit_parents(params: dict):
    parents = []
    if params.get("parent"):
        parents = [params["parent"]]
    else:
        pv = params.get("parameters", {}).get("parent_variant") or params.get("parameters", {}).get("parents")
        if isinstance(pv, list):
            parents = pv
        elif isinstance(pv, str) and pv:
            parents = [pv]

    # Si no hay parents, nada que auditar
    if not parents:
        return


    import re
    phase = params.get("phase")
    if not phase:
        # intentar inferir desde params.yaml path
        import inspect
        frame = inspect.currentframe()
        while frame:
            local_vars = frame.f_locals
            if "args" in local_vars and hasattr(local_vars["args"], "phase"):
                phase = local_vars["args"].phase
                break
            frame = frame.f_back

    # Permitir parent: null o parents: null/lista vacía sólo en f01 y f08
    if phase and re.match(r"^f0?1(_|$)|^f0?8(_|$)", phase):
        if all(p is None for p in parents):
            return
    # Para el resto, error si hay parent None
    if any(p is None for p in parents):
        raise RuntimeError(f"[AUDIT] Se encontró un parent=None en la definición de variante para la fase {phase}. Esto no es válido.")
    # Si la fase es f01* y hay parent no None, error
    if phase and re.match(r"^f0?1(_|$)", phase) and any(p is not None for p in parents):
        raise RuntimeError(f"[AUDIT] La fase {phase} no debe tener parent (solo permitido en fases >1)")

    parent_hashes = params.get("parent_hashes", {})

    for p in parents:
        parent_phase = find_parent_phase(p)
        parent_path = Path("executions") / parent_phase / p / "outputs.yaml"

        if not parent_path.exists():
            raise RuntimeError(f"[AUDIT] Missing outputs.yaml for parent {p}")

        expected = parent_hashes.get(p)
        current = _sha256_file(parent_path)

        if expected and expected != current:
            print("\n[AUDIT ERROR] Parent artifact modified\n")
            print(f"Variant parent: {p}")
            print(f"File: {parent_path}")

            print("\n--- ORIGINAL (registered)")
            print(f"hash={expected}")

            print("\n--- CURRENT")
            print(f"time={_file_mtime(parent_path)} hash={current}")

            print("\n--- DIFF")
            print(_git_diff(parent_path))

            raise RuntimeError("Parent outputs.yaml modified")


def audit_code():
    try:
        changed = subprocess.check_output(
            ["git", "status", "--porcelain", "scripts/"],
            text=True
        ).strip()
    except Exception:
        changed = ""

    if changed:
        print("\n[AUDIT ERROR] Source code modified\n")
        print("\n--- CURRENT STATE")
        print("Uncommitted changes detected in scripts/")

        print("\n--- DIFF")
        print(subprocess.getoutput("git diff scripts/"))

        raise RuntimeError("Source code modified")

if __name__ == "__main__":
    main()
