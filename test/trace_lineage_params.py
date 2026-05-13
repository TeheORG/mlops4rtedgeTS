#!/usr/bin/env python3
"""Genera una tabla de trazabilidad de parámetros a lo largo del linaje de variantes.

Para cada variante hoja (por defecto v70?), recorre su cadena de parents hacia atrás,
agrega los parámetros observados en cada fase y produce una tabla por parámetro con:
  - fase/variante donde aparece por primera vez,
  - valor inicial,
  - valor en la hoja si existe,
  - estado de herencia/redefinición,
  - valores observados en cada fase del linaje.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from io import StringIO
from pathlib import Path
from typing import Any

import yaml


PHASE_ORDER = {
    "f01_explore": 1,
    "f02_events": 2,
    "f03_windows": 3,
    "f04_targets": 4,
    "f05_modeling": 5,
    "f06_quant": 6,
    "f07_modval": 7,
    "f08_sysval": 8,
}

PHASE_COLUMNS = [
    "f01_explore",
    "f02_events",
    "f03_windows",
    "f04_targets",
    "f05_modeling",
    "f06_quant",
    "f07_modval",
    "f08_sysval",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Traza parámetros a través del linaje de una o varias variantes hoja."
    )
    parser.add_argument("--root", required=True, help="Carpeta base de ejecuciones.")
    parser.add_argument(
        "--variant-regex",
        default=r"^v70[0-9]$",
        help="Regex para seleccionar variantes hoja. Por defecto: ^v70[0-9]$",
    )
    parser.add_argument(
        "--leaf-phase",
        default="f07_modval",
        help="Fase donde buscar las variantes hoja. Por defecto: f07_modval",
    )
    parser.add_argument("--output", required=True, help="Ruta de salida (.md o .csv).")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def flatten_mapping(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    flattened: dict[str, Any] = {}
    for key, value in data.items():
        current_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            flattened.update(flatten_mapping(value, current_key))
        else:
            flattened[current_key] = value
    return flattened


def format_value(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
        return str(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def build_variant_index(root: Path) -> dict[str, tuple[str, Path]]:
    index: dict[str, tuple[str, Path]] = {}
    for phase_dir in sorted(
        [path for path in root.iterdir() if path.is_dir() and path.name.startswith("f")],
        key=lambda path: PHASE_ORDER.get(path.name, 999),
    ):
        for variant_dir in sorted([path for path in phase_dir.iterdir() if path.is_dir() and path.name.startswith("v")]):
            index[variant_dir.name] = (phase_dir.name, variant_dir)
    return index


def build_lineage(variant: str, variant_index: dict[str, tuple[str, Path]]) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    current = variant
    seen: set[str] = set()

    while current:
        if current in seen:
            raise RuntimeError(f"Ciclo detectado en el linaje de {variant}: {current}")
        seen.add(current)

        if current not in variant_index:
            raise RuntimeError(f"Variante no encontrada en executions: {current}")

        phase_name, variant_dir = variant_index[current]
        params_yaml = load_yaml(variant_dir / "params.yaml")
        parameters = params_yaml.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}

        lineage.append(
            {
                "phase": phase_name,
                "variant": current,
                "path": variant_dir,
                "params": flatten_mapping(parameters),
                "parent": params_yaml.get("parent"),
            }
        )
        current = params_yaml.get("parent")

    lineage.reverse()
    return lineage


def summarize_status(entries: list[tuple[str, str, Any]], leaf_variant: str) -> tuple[str, str, str, str, str]:
    origin_phase, origin_variant, origin_value = entries[0]
    last_phase, last_variant, last_value = entries[-1]

    distinct_values: list[Any] = []
    for _, _, value in entries:
        if all(value != existing for existing in distinct_values):
            distinct_values.append(value)

    if last_variant == leaf_variant:
        leaf_value = format_value(last_value)
        if len(entries) == 1:
            status = "generado_en_hoja"
        elif len(distinct_values) == 1:
            status = "heredado_sin_cambios"
        else:
            status = "redefinido_en_linaje"
    else:
        leaf_value = "-"
        status = "solo_ancestro"

    changes = []
    previous_value = entries[0][2]
    for phase_name, variant_name, value in entries[1:]:
        if value != previous_value:
            changes.append(f"{phase_name}:{variant_name}")
            previous_value = value

    changed_in = ", ".join(changes) if changes else "-"
    return origin_phase, origin_variant, format_value(origin_value), leaf_value, f"{status}; cambios_en={changed_in}"


def build_rows(root: Path, leaf_phase: str, variant_regex: str) -> list[dict[str, str]]:
    variant_index = build_variant_index(root)
    pattern = re.compile(variant_regex)

    leaf_variants = sorted(
        [
            variant_name
            for variant_name, (phase_name, _) in variant_index.items()
            if phase_name == leaf_phase and pattern.match(variant_name)
        ]
    )

    rows: list[dict[str, str]] = []
    for leaf_variant in leaf_variants:
        lineage = build_lineage(leaf_variant, variant_index)
        entries_by_param: dict[str, list[tuple[str, str, Any]]] = {}

        for node in lineage:
            for key, value in node["params"].items():
                entries_by_param.setdefault(key, []).append((node["phase"], node["variant"], value))

        for param_name in sorted(entries_by_param):
            origin_phase, origin_variant, origin_value, leaf_value, inheritance = summarize_status(
                entries_by_param[param_name],
                leaf_variant,
            )

            row = {
                "leaf_variant": leaf_variant,
                "parameter": param_name,
                "origin_phase": origin_phase,
                "origin_variant": origin_variant,
                "origin_value": origin_value,
                "leaf_value": leaf_value,
                "inheritance": inheritance,
                "history": " -> ".join(
                    f"{phase}:{variant}={format_value(value)}"
                    for phase, variant, value in entries_by_param[param_name]
                ),
            }

            phase_lookup = {phase: f"{variant}={format_value(value)}" for phase, variant, value in entries_by_param[param_name]}
            for phase_name in PHASE_COLUMNS:
                row[phase_name] = phase_lookup.get(phase_name, "-")

            rows.append(row)

    return rows


def render_markdown(rows: list[dict[str, str]]) -> str:
    lines = [
        "# Trazabilidad de parámetros por linaje",
        "",
        "Cada fila representa un parámetro observado en el linaje de una variante hoja v70?.",
        "Se indica dónde aparece por primera vez, su valor original, su valor en la hoja si sigue presente y la traza fase a fase.",
        "",
        f"Filas generadas: {len(rows)}",
        "",
        "| variante hoja | parámetro | fase origen | variante origen | valor origen | valor en hoja | herencia | f01 | f02 | f03 | f04 | f05 | f06 | f07 | historial |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        cells = [
            row["leaf_variant"],
            row["parameter"],
            row["origin_phase"],
            row["origin_variant"],
            row["origin_value"],
            row["leaf_value"],
            row["inheritance"],
            row["f01_explore"],
            row["f02_events"],
            row["f03_windows"],
            row["f04_targets"],
            row["f05_modeling"],
            row["f06_quant"],
            row["f07_modval"],
            row["history"],
        ]
        escaped = [cell.replace("|", "\\|") for cell in cells]
        lines.append("| " + " | ".join(escaped) + " |")

    return "\n".join(lines) + "\n"


def render_csv(rows: list[dict[str, str]]) -> str:
    fieldnames = [
        "leaf_variant",
        "parameter",
        "origin_phase",
        "origin_variant",
        "origin_value",
        "leaf_value",
        "inheritance",
        "f01_explore",
        "f02_events",
        "f03_windows",
        "f04_targets",
        "f05_modeling",
        "f06_quant",
        "f07_modval",
        "history",
    ]

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, delimiter=';')
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key, "") for key in fieldnames})
    return buffer.getvalue()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = Path(args.output).resolve()
    rows = build_rows(root, args.leaf_phase, args.variant_regex)

    rendered = render_csv(rows) if output_path.suffix.lower() == ".csv" else render_markdown(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"Tabla generada en: {output_path}")
    print(f"Filas generadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())