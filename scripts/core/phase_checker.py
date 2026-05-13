import argparse
import re
import sys
from pathlib import Path
from typing import Any

import yaml


SIZE_UNITS = {
    "B": 1,
    "KB": 1024,
    "MB": 1024 * 1024,
    "GB": 1024 * 1024 * 1024,
}


class ValidationError(Exception):
    pass


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ValidationError(f"Spec file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        raise ValidationError(f"Invalid YAML in spec: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValidationError("Spec root must be a YAML mapping")
    return data


def _as_phase_rules(spec: dict[str, Any], phase: str) -> dict[str, Any]:
    phases = spec.get("phases")
    if isinstance(phases, dict):
        rules = phases.get(phase)
    else:
        rules = spec.get(phase)

    if rules is None:
        raise ValidationError(f"No rules found for phase '{phase}' in spec")
    if not isinstance(rules, dict):
        raise ValidationError(f"Rules for phase '{phase}' must be a mapping")
    return rules


def _normalize_files(rules: dict[str, Any]) -> list[dict[str, Any]]:
    raw = rules.get("files", [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValidationError("'files' must be a list")

    normalized: list[dict[str, Any]] = []
    for item in raw:
        if isinstance(item, str):
            normalized.append({"path": item, "required": True})
            continue
        if not isinstance(item, dict):
            raise ValidationError("Each file rule must be string or mapping")
        path = item.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ValidationError("Each file mapping must include non-empty 'path'")
        normalized.append(item)
    return normalized


def _has_glob(pattern: str) -> bool:
    return any(ch in pattern for ch in "*?[]")


def _iter_matches(base: Path, pattern: str) -> list[Path]:
    if _has_glob(pattern):
        return sorted(base.glob(pattern))
    return [base / pattern]


def _size_to_bytes(raw: str) -> int:
    m = re.match(r"^([0-9]*\.?[0-9]+)\s*([A-Za-z]+)?$", raw.strip())
    if not m:
        raise ValidationError(f"Invalid size value: '{raw}'")
    value = float(m.group(1))
    unit = (m.group(2) or "B").upper()
    if unit not in SIZE_UNITS:
        raise ValidationError(f"Unsupported size unit '{unit}' in '{raw}'")
    return int(value * SIZE_UNITS[unit])


def _check_size_expression(file_size: int, expr: str) -> tuple[bool, str]:
    terms = [t.strip() for t in expr.split("&") if t.strip()]
    if not terms:
        return True, ""

    for term in terms:
        m = re.match(r"^(<=|>=|==|=|<|>)\s*([0-9]*\.?[0-9]+\s*[A-Za-z]*)$", term)
        if not m:
            return False, f"Invalid size expression term: '{term}'"
        op = m.group(1)
        rhs = _size_to_bytes(m.group(2))

        ok = {
            "<": file_size < rhs,
            "<=": file_size <= rhs,
            ">": file_size > rhs,
            ">=": file_size >= rhs,
            "=": file_size == rhs,
            "==": file_size == rhs,
        }[op]
        if not ok:
            return False, f"size {file_size}B does not satisfy '{term}'"
    return True, ""


def _read_structured(path: Path) -> Any:
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml", ".json"}:
        try:
            return yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise ValidationError(f"Cannot parse structured file {path}: {exc}") from exc
    raise ValidationError(f"yaml_key checks are supported only for yaml/yml/json files: {path}")


def _get_nested(data: Any, key_path: str) -> tuple[bool, Any]:
    current = data
    for part in key_path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return False, None
    return True, current


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _apply_constraints(value: Any, constraints: list[Any]) -> list[str]:
    errors: list[str] = []
    for rule in constraints:
        if isinstance(rule, str):
            if rule == "not_empty":
                if value in (None, "", [], {}, ()):
                    errors.append("value must not be empty")
            elif rule == "numeric":
                if not _is_number(value):
                    errors.append(f"value must be numeric, got '{value}'")
            elif rule == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    errors.append(f"value must be integer, got '{value}'")
            else:
                errors.append(f"unknown constraint '{rule}'")
            continue

        if isinstance(rule, dict):
            for op, rhs in rule.items():
                if op in {"gt", "gte", "lt", "lte"}:
                    if not _is_number(value):
                        errors.append("numeric comparison requires numeric value")
                        continue
                    if op == "gt" and not (value > rhs):
                        errors.append(f"value {value} must be > {rhs}")
                    if op == "gte" and not (value >= rhs):
                        errors.append(f"value {value} must be >= {rhs}")
                    if op == "lt" and not (value < rhs):
                        errors.append(f"value {value} must be < {rhs}")
                    if op == "lte" and not (value <= rhs):
                        errors.append(f"value {value} must be <= {rhs}")
                elif op == "eq":
                    if op == "eq" and not (value == rhs):
                        errors.append(f"value {value} must be == {rhs}")
                elif op == "neq":
                    if op == "neq" and not (value != rhs):
                        errors.append(f"value {value} must be != {rhs}")
                elif op == "in":
                    if value not in rhs:
                        errors.append(f"value {value} must be one of {rhs}")
                elif op == "regex":
                    if not re.search(str(rhs), str(value)):
                        errors.append(f"value '{value}' does not match regex '{rhs}'")
                else:
                    errors.append(f"unknown constraint operator '{op}'")
            continue

        errors.append(f"invalid constraint format: {rule}")
    return errors


def _check_file_content(path: Path, checks: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    text_cache: str | None = None
    structured_cache: Any = None
    structured_loaded = False

    for check in checks:
        ctype = check.get("type")
        if ctype == "line_contains":
            needle = str(check.get("value", ""))
            if text_cache is None:
                text_cache = path.read_text(encoding="utf-8", errors="replace")
            if needle not in text_cache:
                errors.append(f"missing text '{needle}'")
            continue

        if ctype == "regex":
            pattern = str(check.get("value", ""))
            if text_cache is None:
                text_cache = path.read_text(encoding="utf-8", errors="replace")
            flags = re.MULTILINE
            if not re.search(pattern, text_cache, flags):
                errors.append(f"regex not matched '{pattern}'")
            continue

        if ctype == "yaml_key":
            key_path = str(check.get("key", "")).strip()
            required = bool(check.get("required", True))
            constraints = check.get("constraints", []) or []
            if not key_path:
                errors.append("yaml_key check requires non-empty 'key'")
                continue
            if not structured_loaded:
                structured_cache = _read_structured(path)
                structured_loaded = True
            exists, value = _get_nested(structured_cache, key_path)
            if not exists:
                if required:
                    errors.append(f"missing key '{key_path}'")
                continue
            errors.extend([f"{key_path}: {msg}" for msg in _apply_constraints(value, constraints)])
            continue

        errors.append(f"unknown check type '{ctype}'")

    return errors


def _validate_single_file(file_rule: dict[str, Any], fpath: Path, rel: str) -> list[str]:
    errors: list[str] = []

    if bool(file_rule.get("not_empty", False)):
        if fpath.stat().st_size <= 0:
            msg = f"[⭕️FAIL] empty file: {rel}"
            print(msg)
            errors.append(msg)
        else:
            print(f"[OK] not empty: {rel}")

    size_expr = file_rule.get("size")
    if isinstance(size_expr, str) and size_expr.strip():
        ok, detail = _check_size_expression(fpath.stat().st_size, size_expr)
        if ok:
            print(f"[OK] size: {rel} ({size_expr})")
        else:
            msg = f"[⭕️FAIL] size: {rel} -> {detail}"
            print(msg)
            errors.append(msg)

    checks = file_rule.get("checks", []) or []
    if checks:
        if not isinstance(checks, list) or not all(isinstance(c, dict) for c in checks):
            msg = f"[⭕️FAIL] checks must be a list of mappings: {rel}"
            print(msg)
            errors.append(msg)
            return errors
        try:
            content_errors = _check_file_content(fpath, checks)
        except Exception as exc:
            msg = f"[⭕️FAIL] cannot evaluate checks in {rel}: {exc}"
            print(msg)
            errors.append(msg)
            return errors

        if content_errors:
            for cerr in content_errors:
                msg = f"[⭕️FAIL] {rel}: {cerr}"
                print(msg)
                errors.append(msg)
        else:
            print(f"[OK] content checks: {rel}")

    return errors


def _validate_directory_children(
    variant_dir: Path,
    dir_rule: dict[str, Any],
    matched_dirs: list[Path],
    rel_dir_pattern: str,
) -> list[str]:
    errors: list[str] = []
    children = dir_rule.get("children", []) or []
    if not isinstance(children, list) or not all(isinstance(c, dict) for c in children):
        msg = f"[⭕️FAIL] children must be a list of mappings: {rel_dir_pattern}"
        print(msg)
        return [msg]

    for dpath in matched_dirs:
        rel_dir = dpath.relative_to(variant_dir).as_posix()
        if not dpath.is_dir():
            msg = f"[⭕️FAIL] expected directory match but got file: {rel_dir}"
            print(msg)
            errors.append(msg)
            continue

        for child in children:
            child_rel = str(child.get("path", "")).strip()
            if not child_rel:
                msg = f"[⭕️FAIL] child rule requires non-empty path under: {rel_dir_pattern}"
                print(msg)
                errors.append(msg)
                continue

            child_required = bool(child.get("required", True))
            full = dpath / child_rel
            rel_full = full.relative_to(variant_dir).as_posix()
            if full.exists():
                print(f"[OK] exists: {rel_full}")
                if full.is_file():
                    errors.extend(_validate_single_file(child, full, rel_full))
            elif child_required:
                msg = f"[⭕️FAIL] missing required file: {rel_full}"
                print(msg)
                errors.append(msg)
            else:
                print(f"[SKIP] optional file missing: {rel_full}")

    return errors


def validate_phase(spec_path: Path, phase: str, variant_dir: Path) -> int:
    spec = _load_yaml(spec_path)
    rules = _as_phase_rules(spec, phase)
    files = _normalize_files(rules)

    print(f"\n===== CHECKING {phase} ({variant_dir.name}) with spec =====")
    print(f"[INFO] Spec: {spec_path}")

    errors: list[str] = []

    # Step 1: existence checks first
    existing_paths: list[tuple[dict[str, Any], Path, str]] = []
    directory_rules: list[tuple[dict[str, Any], list[Path], str]] = []
    for file_rule in files:
        rel = file_rule["path"]
        required = bool(file_rule.get("required", True))
        matches = _iter_matches(variant_dir, rel)
        matched_existing = [m for m in matches if m.exists()]

        if "children" in file_rule:
            if matched_existing:
                print(f"[OK] exists: {rel} ({len(matched_existing)} match(es))")
                directory_rules.append((file_rule, matched_existing, rel))
            elif required:
                msg = f"[⭕️FAIL] missing required directory pattern: {rel}"
                print(msg)
                errors.append(msg)
            else:
                print(f"[SKIP] optional directory pattern missing: {rel}")
            continue

        if matched_existing:
            for m in matched_existing:
                rel_path = m.relative_to(variant_dir).as_posix()
                print(f"[OK] exists: {rel_path}")
                existing_paths.append((file_rule, m, rel_path))
        elif required:
            msg = f"[⭕️FAIL] missing required file: {rel}"
            print(msg)
            errors.append(msg)
        else:
            print(f"[SKIP] optional file missing: {rel}")

    # Step 2: content and size checks only for existing files
    for file_rule, fpath, rel in existing_paths:
        if fpath.is_file():
            errors.extend(_validate_single_file(file_rule, fpath, rel))

    for dir_rule, matched_dirs, rel_dir_pattern in directory_rules:
        errors.extend(_validate_directory_children(variant_dir, dir_rule, matched_dirs, rel_dir_pattern))

    print("\n======####@@@@@@@@@@@@####======")
    if errors:
        print(f"❌[ERROR] Validation failed with {len(errors)} issue(s)")
        print("======####@@@@@@@@@@@@####======\n")
        return 1
    print("✅[SUCCESS] Validation passed")
    print("======####@@@@@@@@@@@@####======\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase artifact checker from YAML spec")
    parser.add_argument("--spec", required=True, help="Path to checker YAML spec")
    parser.add_argument("--phase", required=True, help="Phase name, e.g. f01_explore")
    parser.add_argument("--variant-dir", required=True, help="Absolute or relative path to variant directory")
    args = parser.parse_args()

    return validate_phase(Path(args.spec), args.phase, Path(args.variant_dir))


if __name__ == "__main__":
    sys.exit(main())
