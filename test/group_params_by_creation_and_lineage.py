#!/usr/bin/env python3
"""Agrupa parámetros por variante de creación y valor, mostrando linajes que los usan.

Salida principal: tabla Markdown/CSV con grupos de la forma:
  (parametro_canonico, fase_creacion, variante_creacion, valor_creacion)
e indicando qué variantes hoja (linajes) lo reciben/usan.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
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

TARGET_PARAMS: dict[str, list[str]] = {
    "Tu": ["Tu"],
    "event_type_count": ["event_type_count"],
    "OW": ["OW"],
    "LT": ["LT"],
    "PW": ["PW"],
    "prediction_name": ["prediction_name"],
    "model_family": ["model_family"],
    "trainable": ["trainable"],
    "decision_threshold": ["decision_threshold"],
    "best_recall": ["best_recall", "best_val_recall", "selection_global_recall", "test_recall"],
    "best_precision": ["best_precision", "best_val_precision", "selection_global_precision", "test_precision"],
    "edge_capable": ["edge_capable", "configuration_edge_capable"],
    "model_size_bytes": ["model_size_bytes", "total_model_size_bytes"],
    "arena_estimada_bytes": ["arena_estimada_bytes", "arena_estimated_bytes", "required_arena_bytes"],
    "footprint_estimated_bytes": ["footprint_estimated_bytes"],
    "operators": ["operators", "operators_union"],
    "quality_score": ["quality_score", "system_quality_score", "mean_model_quality_score"],
    "itmax_ms": ["itmax_ms", "MTI_MS", "max_exec_time_ms"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Agrupa parametros por variante de creacion y valor, con sus linajes receptores."
    )
    parser.add_argument("--root", required=True, help="Carpeta base de executions.")
    parser.add_argument(
        "--leaf-phase",
        default="f07_modval",
        help="Fase hoja para construir linajes (default: f07_modval).",
    )
    parser.add_argument(
        "--leaf-regex",
        default=r"^v70[0-9]$",
        help="Regex de variantes hoja (default: ^v70[0-9]$).",
    )
    parser.add_argument("--output", required=True, help="Ruta de salida (.md o .csv).")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def flatten_mapping(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        full = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_mapping(value, full))
        else:
            out[full] = value
    return out


def fmt(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, str):
        return str(value)
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def build_variant_index(root: Path) -> dict[str, tuple[str, Path]]:
    idx: dict[str, tuple[str, Path]] = {}
    phase_dirs = [path for path in root.iterdir() if path.is_dir() and path.name.startswith("f")]
    phase_dirs.sort(key=lambda p: PHASE_ORDER.get(p.name, 999))
    for phase_dir in phase_dirs:
        for variant_dir in sorted([p for p in phase_dir.iterdir() if p.is_dir() and p.name.startswith("v")]):
            idx[variant_dir.name] = (phase_dir.name, variant_dir)
    return idx


def build_lineage(leaf_variant: str, variant_index: dict[str, tuple[str, Path]]) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    cur = leaf_variant
    seen: set[str] = set()

    while cur:
        if cur in seen:
            raise RuntimeError(f"Ciclo detectado para {leaf_variant}: {cur}")
        seen.add(cur)
        if cur not in variant_index:
            raise RuntimeError(f"Variante no encontrada: {cur}")

        phase, vdir = variant_index[cur]
        params_yaml = load_yaml(vdir / "params.yaml")
        outputs_yaml = load_yaml(vdir / "outputs.yaml")

        params = params_yaml.get("parameters") if isinstance(params_yaml.get("parameters"), dict) else {}
        exports = outputs_yaml.get("exports") if isinstance(outputs_yaml.get("exports"), dict) else {}

        lineage.append(
            {
                "phase": phase,
                "variant": cur,
                "params": flatten_mapping(params),
                "exports": flatten_mapping(exports),
                "parent": params_yaml.get("parent"),
            }
        )
        cur = params_yaml.get("parent")

    lineage.reverse()
    return lineage


def find_first_alias(node: dict[str, Any], aliases: list[str]) -> tuple[str, Any] | None:
    params = node["params"]
    exports = node["exports"]

    for alias in aliases:
        if alias in params:
            return alias, params[alias]
    for alias in aliases:
        if alias in exports:
            return alias, exports[alias]
    return None


def collect_param_info(lineage: list[dict[str, Any]], aliases: list[str]) -> dict[str, Any] | None:
    creation = None
    use_nodes: list[str] = []

    for node in lineage:
        found = find_first_alias(node, aliases)
        if found is None:
            continue

        alias_key, alias_value = found
        if creation is None:
            creation = {
                "phase": node["phase"],
                "variant": node["variant"],
                "alias": alias_key,
                "value": alias_value,
            }

        # "recibe/usa" = aparece en params del nodo (uso directo), o en exports si no existe en params.
        if any(alias in node["params"] for alias in aliases):
            use_nodes.append(f"{node['phase']}:{node['variant']}[params]")
        elif any(alias in node["exports"] for alias in aliases):
            use_nodes.append(f"{node['phase']}:{node['variant']}[exports]")

    if creation is None:
        return None

    return {
        "creation_phase": creation["phase"],
        "creation_variant": creation["variant"],
        "creation_alias": creation["alias"],
        "creation_value": creation["value"],
        "use_nodes": use_nodes,
    }


def build_grouped_rows(root: Path, leaf_phase: str, leaf_regex: str) -> list[dict[str, str]]:
    variant_index = build_variant_index(root)
    pattern = re.compile(leaf_regex)

    leaf_variants = sorted(
        [
            variant
            for variant, (phase, _) in variant_index.items()
            if phase == leaf_phase and pattern.match(variant)
        ]
    )

    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    not_found: defaultdict[str, list[str]] = defaultdict(list)

    for leaf in leaf_variants:
        lineage = build_lineage(leaf, variant_index)

        for canonical, aliases in TARGET_PARAMS.items():
            info = collect_param_info(lineage, aliases)
            if info is None:
                not_found[canonical].append(leaf)
                continue

            group_key = (
                canonical,
                info["creation_phase"],
                info["creation_variant"],
                fmt(info["creation_value"]),
            )

            if group_key not in grouped:
                grouped[group_key] = {
                    "parameter": canonical,
                    "creation_phase": info["creation_phase"],
                    "creation_variant": info["creation_variant"],
                    "creation_alias": info["creation_alias"],
                    "creation_value": fmt(info["creation_value"]),
                    "lineages": set(),
                    "use_nodes": set(),
                }

            grouped[group_key]["lineages"].add(leaf)
            for node in info["use_nodes"]:
                grouped[group_key]["use_nodes"].add(node)

    rows: list[dict[str, str]] = []
    for key in sorted(grouped):
        item = grouped[key]
        lineages_sorted = sorted(item["lineages"])
        use_nodes_sorted = sorted(item["use_nodes"])

        rows.append(
            {
                "creation_phase": item["creation_phase"],
                "parameter": item["parameter"],
                "creation_variant": item["creation_variant"],
                "creation_value": item["creation_value"],
                "lineages": ", ".join(lineages_sorted),
            }
        )

    # Añade una fila explícita para parámetros no encontrados, para que el informe quede completo.
    for canonical in TARGET_PARAMS:
        if canonical not in {row["parameter"] for row in rows}:
            leaves = sorted(not_found.get(canonical, []))
            rows.append(
                {
                    "creation_phase": "-",
                    "parameter": canonical,
                    "creation_variant": "-",
                    "creation_value": "-",
                    "lineages": ", ".join(leaves) if leaves else "-",
                }
            )

    rows.sort(key=lambda r: (r["creation_phase"], r["parameter"], r["creation_variant"], r["creation_value"]))
    return rows


def render_markdown(rows: list[dict[str, str]], leaf_phase: str, leaf_regex: str) -> str:
    grouped: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[(row["creation_phase"], row["parameter"])].append(row)

    lines = [
        "# Tabla por Parametro: Creacion y Linajes que lo Usan",
        "",
        f"Fase hoja analizada: {leaf_phase}",
        f"Filtro de variantes hoja: `{leaf_regex}`",
        "",
        "Agrupacion: mismo parametro + misma variante de creacion + mismo valor de creacion.",
        "Vista de prueba: 3 columnas (fase-crea, param, detalle multilinea).",
        "",
        f"Filas base: {len(rows)}",
        f"Filas agrupadas para visualizacion: {len(grouped)}",
        "",
        "| fase-crea | param | detalle (variant-crea | value | linaje) |",
        "| --- | --- | --- |",
    ]

    for (creation_phase, parameter) in sorted(grouped.keys()):
        entries = grouped[(creation_phase, parameter)]
        detail_lines = []
        for entry in entries:
            detail_lines.append(
                f"{entry['creation_variant']} | {entry['creation_value']} | {entry['lineages']}"
            )
        detail = "<br>".join(line.replace("|", "\\|") for line in detail_lines)
        lines.append(
            "| {phase} | {param} | {detail} |".format(
                phase=creation_phase.replace("|", "\\|"),
                param=parameter.replace("|", "\\|"),
                detail=detail,
            )
        )

    return "\n".join(lines) + "\n"


def render_csv(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=headers, delimiter=';')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    rows = build_grouped_rows(root, args.leaf_phase, args.leaf_regex)
    rendered = render_csv(rows) if output.suffix.lower() == ".csv" else render_markdown(rows, args.leaf_phase, args.leaf_regex)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    print(f"Salida generada en: {output}")
    print(f"Filas agrupadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())