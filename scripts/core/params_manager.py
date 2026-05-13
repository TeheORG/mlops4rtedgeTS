import json
import yaml
import shutil
import re
from datetime import datetime, timezone
from pathlib import Path
from scripts.core.schema_utils import load_traceability_schema
import hashlib

# ===============================================================
# PATHS
# ===============================================================

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VARIANT_ID_REGEX = re.compile(r"^v(?P<phase>\d)_(?P<seq>\d{4})$")


# ===============================================================
# SCHEMA LOADING
# ===============================================================

def load_schema():
    return load_traceability_schema()


def _extract_phase_code(phase_name: str) -> str | None:
    m = re.match(r"^f(\d{2})(?:_|$)", phase_name)
    return str(int(m.group(1))) if m else None


def validate_variant_id_for_phase(variant: str, phase: str, field_name: str = "VARIANT") -> None:
    m = VARIANT_ID_REGEX.fullmatch(str(variant).strip())
    if not m:
        raise ValueError(
            f"Formato inválido para {field_name}: {variant}. Debe ser vY_XXXX (ej. v1_0001)"
        )

    phase_code = _extract_phase_code(phase)
    if phase_code and m.group("phase") != phase_code:
        raise ValueError(
            f"{field_name}={variant} no corresponde a la fase {phase} (se esperaba prefijo v{phase_code}_)"
        )


def normalize_variant_id_for_phase(raw_variant: str, phase: str, field_name: str = "VARIANT") -> str:
    raw = str(raw_variant).strip()
    phase_code = _extract_phase_code(phase)
    if not phase_code:
        raise ValueError(f"No se pudo inferir fase para normalizar {field_name}: {phase}")

    # Canonical form: vY_XXXX
    m = VARIANT_ID_REGEX.fullmatch(raw)
    if m:
        if m.group("phase") != phase_code:
            raise ValueError(
                f"{field_name}={raw} no corresponde a la fase {phase} (se esperaba prefijo v{phase_code}_)"
            )
        return f"v{m.group('phase')}_{m.group('seq')}"

    # Shorthand form: vNNNN | vNNN | vNN | vN | NNNN | NNN | NN | N
    short = re.fullmatch(r"v?([0-9]{1,4})", raw)
    if short:
        num = int(short.group(1))
        return f"v{phase_code}_{num:04d}"

    raise ValueError(
        f"Formato inválido para {field_name}: {raw}. Usa vY_XXXX o abreviado vNNNN/NNNN"
    )


# ===============================================================
# TYPE SYSTEM
# ===============================================================

def parse_value_by_rule(raw_value: str, rule: dict, key: str):

    expected = rule.get("type")

    if expected == "string":
        # No conversión automática, se guarda tal cual
        return str(raw_value)

    if expected == "integer":
        if not re.fullmatch(r"-?\d+", raw_value.strip()):
            raise ValueError(f"{key} debe ser integer")
        return int(raw_value)

    if expected == "float":
        try:
            return float(raw_value)
        except ValueError:
            raise ValueError(f"{key} debe ser float")

    if expected == "number":
        try:
            if "." in raw_value:
                return float(raw_value)
            return int(raw_value)
        except ValueError:
            raise ValueError(f"{key} debe ser number")

    if expected in ("list", "dict"):
        try:
            value = yaml.safe_load(raw_value)
        except Exception:
            raise ValueError(f"{key} debe ser YAML válido ({expected})")

        # Soporte práctico para CLI: permitir listas en formato CSV
        # (ej. parents=v700,v701,v703) además de YAML ([v700, v701, v703]).
        if expected == "list" and not isinstance(value, list):
            raw_csv = str(raw_value).strip()
            if raw_csv and "," in raw_csv and not raw_csv.startswith("["):
                value = [item.strip() for item in raw_csv.split(",") if item.strip()]

        if expected == "list" and not isinstance(value, list):
            raise ValueError(f"{key} debe ser list")

        if expected == "dict" and not isinstance(value, dict):
            raise ValueError(f"{key} debe ser dict")

        if expected == "dict" and isinstance(value, dict):
            if value and all(v is None for v in value.values()) and any(":" in str(k) for k in value.keys()):
                repaired = {}
                repaired_ok = True

                for malformed_key in value.keys():
                    if not isinstance(malformed_key, str) or ":" not in malformed_key:
                        repaired_ok = False
                        break

                    left, right = malformed_key.split(":", 1)
                    left = left.strip()
                    right = right.strip()

                    if not left:
                        repaired_ok = False
                        break

                    try:
                        repaired[left] = yaml.safe_load(right)
                    except Exception:
                        repaired[left] = right

                if repaired_ok and repaired:
                    value = repaired

        return value

    raise ValueError(f"Tipo no soportado en schema: {expected}")


def validate_type(value, rule, key):

    expected = rule.get("type")

    if value is None:
        if rule.get("nullable", False):
            return
        raise ValueError(f"{key} no puede ser null")

    if expected == "string":
        if not isinstance(value, str):
            raise ValueError(f"{key} debe ser string")

    elif expected == "integer":
        if not isinstance(value, int):
            raise ValueError(f"{key} debe ser integer")

    elif expected == "float":
        if not isinstance(value, float):
            raise ValueError(f"{key} debe ser float")

    elif expected == "number":
        if not isinstance(value, (int, float)):
            raise ValueError(f"{key} debe ser number")

    elif expected == "list":
        if not isinstance(value, list):
            raise ValueError(f"{key} debe ser list")
        item_rule = rule.get("items")
        if item_rule:
            for v in value:
                validate_type(v, item_rule, f"{key}[]")

    elif expected == "dict":
        if not isinstance(value, dict):
            raise ValueError(f"{key} debe ser dict")
        value_rule = rule.get("values")
        if value_rule:
            for v in value.values():
                validate_type(v, value_rule, f"{key} value")

    # allowed values
    if "allowed" in rule:
        if value not in rule["allowed"]:
            raise ValueError(f"{key} debe ser uno de {rule['allowed']}")

    # regex for strings
    if "regex" in rule and isinstance(value, str):
        if not re.fullmatch(rule["regex"], value):
            raise ValueError(f"{key} no cumple regex {rule['regex']}")

    # simple numeric check
    if "check" in rule and isinstance(value, (int, float)):
        cond = rule["check"]
        if cond.startswith(">="):
            if not value >= float(cond[2:]):
                raise ValueError(f"{key} debe cumplir {cond}")
        elif cond.startswith(">"):
            if not value > float(cond[1:]):
                raise ValueError(f"{key} debe cumplir {cond}")


# ===============================================================
# PARENT PHASE INFERENCE
# ===============================================================

def infer_parent_phase(schema: dict, phase: str):
    """
    Intenta determinar la fase padre a partir del schema.
    Regla:
      - Si la fase tiene parent_phase explícito → usarlo.
      - Si no, se busca la fase f(N-1)_* cuando la fase es fNN_*.
      - Si no se puede inferir, devuelve None.
    """
    phases = schema.get("phases", {})
    phase_schema = phases.get(phase, {})

    explicit = phase_schema.get("parent_phase")
    if explicit:
        return explicit

    # Soporta ambos formatos de nombre de fase:
    #   - f07_modval
    #   - f07modval
    m = re.match(r"^f(\d{2})(?:_|[A-Za-z]|$)", phase)
    if not m:
        return None

    idx = int(m.group(1))
    if idx <= 1:
        return None

    prefix = f"f{idx-1:02d}_"
    candidates = [name for name in phases.keys() if name.startswith(prefix)]

    if len(candidates) == 1:
        return candidates[0]

    return None


# ===============================================================
# PARAM RESOLUTION
# ===============================================================

def resolve_params(phase, provided, parent_params=None):

    schema = load_schema()

    if "phases" not in schema or phase not in schema["phases"]:
        raise RuntimeError(f"No existe definición de fase en schema: {phase}")

    phase_schema = schema["phases"][phase]
    parameters = phase_schema.get("parameters", {})

    resolved = {}

    # Detectar parámetros desconocidos (solo params de fase, PARENT va fuera)
    unknown = set(provided.keys()) - set(parameters.keys())
    if unknown:
        raise ValueError(f"Parámetros no permitidos para {phase}: {sorted(unknown)}")

    for key, rule in parameters.items():

        required = rule.get("required", False)
        inherited = rule.get("inherited", False)
        has_default = "default" in rule

        # 1️⃣ valor indicado por el usuario
        if key in provided:
            value = provided[key]

        # 2️⃣ heredado del parent (params + exports)
        elif inherited and parent_params and key in parent_params:
            value = parent_params[key]

        # 3️⃣ valor por defecto
        elif has_default:
            value = rule["default"]

        # 4️⃣ error si required
        elif required:
            if inherited:
                raise ValueError(
                    f"Falta parámetro obligatorio heredado: {key}. "
                    f"Verifica que la variante padre tenga outputs.yaml generado."
                )
            raise ValueError(f"Falta parámetro obligatorio: {key}")

        else:
            # opcional no definido
            continue

        # Validar tipo final
        validate_type(value, rule, key)

        resolved[key] = value

    return resolved


# ===============================================================
# PARSE --set-args (compatible con make actual)
# ===============================================================

def parse_set_args(raw_set_args: str):

    text = (raw_set_args or "").strip()
    if not text:
        return []

    key_pattern = re.compile(
        r"(?:^|\s)([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)="
    )
    matches = list(key_pattern.finditer(text))
    if not matches:
        raise ValueError("--set-args no contiene pares key=value válidos")

    parsed = []
    for index, match in enumerate(matches):
        start = match.start(1)
        end = matches[index + 1].start(1) if index + 1 < len(matches) else len(text)
        token = text[start:end].strip()
        if "=" not in token:
            continue
        parsed.append(token)

    return parsed


# ============================
# AUDIT SUPPORT (PARENT HASHES)
# ============================


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def compute_parent_hashes(phase: str, params: dict) -> dict:
    parents = []
    if params.get("parent"):
        parents = [params["parent"]]
    else:
        pv = params.get("parameters", {}).get("parent_variant")
        if isinstance(pv, list):
            parents = pv
        elif isinstance(pv, str) and pv:
            parents = [pv]

    hashes = {}
    schema = load_schema()
    parent_phase = infer_parent_phase(schema, phase)

    # Fase 1: no debe tener parent
    if parent_phase is None:
        if parents:
            raise RuntimeError(f"La fase {phase} no debe tener parent (solo permitido en fases >1)")
        return hashes  # vacío

    # Fases >1: deben tener parent
    if not parents:
        raise RuntimeError(f"La fase {phase} requiere parent (obligatorio en fases >1)")

    for p in parents:
        parent_outputs = Path("executions") / parent_phase / p / "outputs.yaml"
        if parent_outputs.exists():
            hashes[p] = _sha256_file(parent_outputs)
    return hashes
    
# ===============================================================
# PARAMS MANAGER
# ===============================================================

class ParamsManager:

    def __init__(self, phase: str):

        self.phase = phase
        self.phase_dir = PROJECT_ROOT / "executions" / phase
        self.phase_dir.mkdir(parents=True, exist_ok=True)

        self._current_variant = None
        self._current_variant_dir = None


    # -----------------------------------------------------------
    # Crear variante
    # -----------------------------------------------------------

    def create_variant(self, variant: str, extra_params=None):
        variant = normalize_variant_id_for_phase(variant, self.phase, "VARIANT")

        variant_dir = self.phase_dir / variant

        if variant_dir.exists():
            raise RuntimeError(f"La carpeta ya existe: {variant_dir}")

        # -----------------------------------------------------------
        # Cargar schema
        # -----------------------------------------------------------

        schema = load_schema()

        if "phases" not in schema or self.phase not in schema["phases"]:
            raise RuntimeError(f"No existe definición de fase en schema: {self.phase}")

        phase_schema = schema["phases"][self.phase]
        parameters_schema = phase_schema.get("parameters", {})
        parent_required = phase_schema.get("parent_required", True)
        parent_phase = infer_parent_phase(schema, self.phase)

        global_schema = schema.get("global", {})
        parent_rule = global_schema.get("PARENT")

        # -----------------------------------------------------------
        # Parseo endurecido de parámetros de usuario
        #   - PARENT (global) → parent_variant
        #   - resto → parámetros de fase
        # -----------------------------------------------------------

        provided = {}
        nested_updates = {}
        parent_variant = None

        if extra_params:
            for item in extra_params:

                key, raw_value = item.split("=", 1)

                if raw_value is None or not str(raw_value).strip():
                    continue

                # PARENT se trata como parámetro global, no de fase
                if key == "PARENT":
                    if not parent_phase:
                        raise ValueError(f"La fase {self.phase} no admite PARENT")

                    parent_variant = normalize_variant_id_for_phase(raw_value, parent_phase, "PARENT")

                    if parent_rule:
                        validate_type(parent_variant, parent_rule, "PARENT")
                    continue

                # Soporte para sintaxis anidada: deployment.target=esp32
                if "." in key:
                    root_key, nested_key = key.split(".", 1)

                    if root_key not in parameters_schema:
                        raise ValueError(
                            f"Parámetro no permitido para {self.phase}: {key}"
                        )

                    root_rule = parameters_schema[root_key]
                    if root_rule.get("type") != "dict":
                        raise ValueError(
                            f"Parámetro no permite subclaves para {self.phase}: {root_key}"
                        )

                    try:
                        nested_value = yaml.safe_load(raw_value)
                    except Exception:
                        nested_value = raw_value

                    nested_updates.setdefault(root_key, {})[nested_key] = nested_value
                    continue

                # Solo se permiten parámetros definidos en la fase
                if key not in parameters_schema:
                    raise ValueError(
                        f"Parámetro no permitido para {self.phase}: {key}"
                    )

                rule = parameters_schema[key]
                value = parse_value_by_rule(raw_value, rule, key)

                provided[key] = value

        for root_key, updates in nested_updates.items():
            base_value = provided.get(root_key, {})
            if base_value is None:
                base_value = {}
            if not isinstance(base_value, dict):
                raise ValueError(
                    f"{root_key} debe ser dict para aplicar subclaves"
                )

            merged_value = dict(base_value)
            merged_value.update(updates)
            provided[root_key] = merged_value

        # parent_variant se maneja como metadato global (PARENT), pero algunas
        # fases legacy todavía lo declaran en su schema de parámetros.
        # Solo lo inyectamos cuando la fase lo espera explícitamente.
        if parent_variant is not None and "parent_variant" in parameters_schema:
            provided["parent_variant"] = parent_variant

        # -----------------------------------------------------------
        # Validar PARENT según parent_required
        # -----------------------------------------------------------

        # Para fases multi-parent (mode: multi), los parents se pasan como
        # parámetro regular (parent_variant=[...]), no via PARENT= key.
        # La validación la hace resolve_params al tratar parent_variant como
        # parámetro required.
        is_multi_parent = (
            parameters_schema.get("parent_variant", {}).get("mode") == "multi"
        )

        if parent_required and not parent_variant and not is_multi_parent:
            raise ValueError(
                f"La fase {self.phase} requiere PARENT=vY_XXXX (variante de la fase anterior)"
            )

        if not parent_required and parent_variant is None:
            # F01, por ejemplo: no tiene parent
            pass

        # -----------------------------------------------------------
        # Resolver parámetros heredados (parent_params)
        #   - Se combinan params.yaml (parameters) + outputs.yaml (exports)
        # -----------------------------------------------------------

        parent_params = None

        if parent_variant:

            parent_phase = infer_parent_phase(schema, self.phase)
            if not parent_phase:
                raise RuntimeError(
                    f"No se pudo inferir fase padre para {self.phase} al usar PARENT={parent_variant}"
                )

            parent_dir = PROJECT_ROOT / "executions" / parent_phase / parent_variant

            if not parent_dir.exists():
                raise RuntimeError(
                    f"No existe la variante padre {parent_phase}:{parent_variant}"
                )

            # params de la fase padre
            parent_params_path = parent_dir / "params.yaml"
            parent_params_data = {}
            if parent_params_path.exists():
                parent_data = yaml.safe_load(parent_params_path.read_text()) or {}
                parent_params_data = parent_data.get("parameters", {}) or {}

            # exports de la fase padre
            parent_exports_path = parent_dir / "outputs.yaml"
            parent_exports_data = {}
            if parent_exports_path.exists():
                parent_out = yaml.safe_load(parent_exports_path.read_text()) or {}
                parent_exports_data = parent_out.get("exports", {}) or {}

            # combinación: params + exports (exports pueden sobrescribir si mismo nombre)
            parent_params = {**parent_params_data, **parent_exports_data}

        # -----------------------------------------------------------
        # Resolución formal (usuario + herencia + default)
        # -----------------------------------------------------------

        resolved_parameters = resolve_params(
            self.phase,
            provided,
            parent_params=parent_params
        )

        # -----------------------------------------------------------
        # Construcción params.yaml autocontenido
        # -----------------------------------------------------------

        final_params = {
            "phase": self.phase,
            "variant": variant,
            "parent": parent_variant,
            "parameters": resolved_parameters
        }

        # ============================
        # AUDIT: store parent hashes
        # ============================


        try:
            parent_hashes = compute_parent_hashes(self.phase, final_params)
            final_params["parent_hashes"] = parent_hashes
        except Exception as e:
            print(f"[WARN] Could not compute parent hashes: {e}")


        # -----------------------------------------------------------
        # CREAR CARPETA SOLO AHORA (tras validación completa)
        # -----------------------------------------------------------

        variant_dir.mkdir(parents=True)

        params_path = variant_dir / "params.yaml"

        yaml.safe_dump(
            final_params,
            params_path.open("w"),
            sort_keys=False
        )

        metadata_path = variant_dir / "metadata.yaml"
        yaml.safe_dump(
            {
                "created_at": datetime.now(timezone.utc).isoformat(),
                "params_path": str(params_path.relative_to(PROJECT_ROOT)),
            },
            metadata_path.open("w"),
            sort_keys=False,
        )

        print(f"[OK] Variante creada: {self.phase}:{variant}")

    # -----------------------------------------------------------
    # Eliminar variante
    # -----------------------------------------------------------

    def delete_variant(self, variant: str):
        validate_variant_id_for_phase(variant, self.phase)
        variant_dir = self.phase_dir / variant
        if not variant_dir.exists():
            raise ValueError("Variante inexistente")

        shutil.rmtree(variant_dir)

        print(f"[OK] Variante eliminada: {variant}")


    # -----------------------------------------------------------
    # Selección
    # -----------------------------------------------------------

    def set_current(self, variant: str):

        vdir = self.phase_dir / variant
        if not vdir.exists():
            raise RuntimeError(f"La variante {variant} no existe")

        self._current_variant = variant
        self._current_variant_dir = vdir


    # -----------------------------------------------------------
    # Guardado metadata
    # -----------------------------------------------------------

    def save_metadata(self, metadata: dict):

        if not self._current_variant_dir:
            raise RuntimeError("No hay variante activa")

        path = self._current_variant_dir / f"{self.phase}_metadata.json"
        json.dump(metadata, path.open("w"), indent=2)
        return path


# ===============================================================
# CLI
# ===============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")

    p_create = sub.add_parser("create")
    p_create.add_argument("--phase", required=True)
    p_create.add_argument("--variant", required=True)
    p_create.add_argument("--set", action="append")
    p_create.add_argument("--set-args")

    p_delete = sub.add_parser("delete")
    p_delete.add_argument("--phase", required=True)
    p_delete.add_argument("--variant", required=True)

    args = parser.parse_args()

    if args.cmd == "create":
        pm = ParamsManager(args.phase)

        merged_sets = list(args.set or [])

        if args.set_args:
            merged_sets.extend(parse_set_args(args.set_args))

        pm.create_variant(args.variant, merged_sets)

    elif args.cmd == "delete":
        pm = ParamsManager(args.phase)
        pm.delete_variant(args.variant)

    else:
        parser.print_help()