#!/usr/bin/env python3
"""Compara herencia real en enlaces parent->child.

Regla de comparación por enlace:
  - Parent: keys de outputs.yaml -> exports
  - Child:  keys de params.yaml -> parameters
  - Se analizan solo claves en la intersección.

Pensado para variantes hoja v70? (f07_modval) pero configurable por CLI.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter, defaultdict
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara intersección outputs(exports) parent vs params(parameters) child."
    )
    parser.add_argument("--root", required=True, help="Carpeta base de ejecuciones.")
    parser.add_argument("--leaf-phase", default="f07_modval", help="Fase hoja (default: f07_modval).")
    parser.add_argument("--leaf-regex", default=r"^v70[0-9]$", help="Regex de variantes hoja.")
    parser.add_argument("--output", required=True, help="Salida .md o .csv")
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data or {}


def flatten_mapping(data: dict[str, Any], prefix: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            out.update(flatten_mapping(value, full_key))
        else:
            out[full_key] = value
    return out


def fmt(value: Any) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float, str)):
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
    chain: list[dict[str, Any]] = []
    cur = leaf_variant
    seen: set[str] = set()

    while cur:
        if cur in seen:
            raise RuntimeError(f"Ciclo detectado en linaje de {leaf_variant}: {cur}")
        seen.add(cur)

        if cur not in variant_index:
            raise RuntimeError(f"Variante no encontrada: {cur}")

        phase, vdir = variant_index[cur]
        params_yaml = load_yaml(vdir / "params.yaml")
        outputs_yaml = load_yaml(vdir / "outputs.yaml")

        params = params_yaml.get("parameters") if isinstance(params_yaml.get("parameters"), dict) else {}
        exports = outputs_yaml.get("exports") if isinstance(outputs_yaml.get("exports"), dict) else {}

        chain.append(
            {
                "phase": phase,
                "variant": cur,
                "parent": params_yaml.get("parent"),
                "params": flatten_mapping(params),
                "exports": flatten_mapping(exports),
            }
        )
        cur = params_yaml.get("parent")

    chain.reverse()
    return chain


def compare_edges(root: Path, leaf_phase: str, leaf_regex: str):
    variant_index = build_variant_index(root)
    pattern = re.compile(leaf_regex)

    leaves = sorted(
        [
            variant
            for variant, (phase, _) in variant_index.items()
            if phase == leaf_phase and pattern.match(variant)
        ]
    )

    detail_rows: list[dict[str, str]] = []
    summary = defaultdict(Counter)

    for leaf in leaves:
        lineage = build_lineage(leaf, variant_index)
        for i in range(len(lineage) - 1):
            parent_node = lineage[i]
            child_node = lineage[i + 1]

            edge_label = f"{parent_node['phase']}->{child_node['phase']}"
            common = sorted(set(parent_node["exports"]) & set(child_node["params"]))

            summary[(leaf, edge_label)]["parent_exports"] = len(parent_node["exports"])
            summary[(leaf, edge_label)]["child_params"] = len(child_node["params"])
            summary[(leaf, edge_label)]["common"] = len(common)

            for key in common:
                p_val = parent_node["exports"].get(key)
                c_val = child_node["params"].get(key)
                equal = p_val == c_val

                detail_rows.append(
                    {
                        "leaf_variant": leaf,
                        "edge": edge_label,
                        "parent_variant": parent_node["variant"],
                        "child_variant": child_node["variant"],
                        "param": key,
                        "parent_output_value": fmt(p_val),
                        "child_param_value": fmt(c_val),
                        "equal": "si" if equal else "no",
                    }
                )
                summary[(leaf, edge_label)]["equal" if equal else "different"] += 1

    summary_rows: list[dict[str, str]] = []
    aggregated = defaultdict(Counter)
    for (leaf, edge_label), cnt in summary.items():
        equal = int(cnt.get("equal", 0))
        diff = int(cnt.get("different", 0))
        common = int(cnt.get("common", 0))
        consistency = (equal / common * 100.0) if common else 0.0

        summary_rows.append(
            {
                "leaf_variant": leaf,
                "edge": edge_label,
                "parent_exports": str(int(cnt.get("parent_exports", 0))),
                "child_params": str(int(cnt.get("child_params", 0))),
                "common_keys": str(common),
                "equal_values": str(equal),
                "different_values": str(diff),
                "consistency_pct": f"{consistency:.1f}",
            }
        )

        aggregated[edge_label]["parent_exports"] += int(cnt.get("parent_exports", 0))
        aggregated[edge_label]["child_params"] += int(cnt.get("child_params", 0))
        aggregated[edge_label]["common"] += common
        aggregated[edge_label]["equal"] += equal
        aggregated[edge_label]["different"] += diff
        aggregated[edge_label]["count"] += 1

    compact_rows: list[dict[str, str]] = []
    for edge_label in sorted(aggregated):
        cnt = aggregated[edge_label]
        n = int(cnt.get("count", 1))
        common = int(cnt.get("common", 0))
        equal = int(cnt.get("equal", 0))
        diff = int(cnt.get("different", 0))
        compact_rows.append(
            {
                "edge": edge_label,
                "leaf_count": str(n),
                "avg_parent_exports": f"{cnt.get('parent_exports', 0) / n:.1f}",
                "avg_child_params": f"{cnt.get('child_params', 0) / n:.1f}",
                "common_keys_total": str(common),
                "equal_values_total": str(equal),
                "different_values_total": str(diff),
                "consistency_pct": f"{(equal / common * 100.0) if common else 0.0:.1f}",
            }
        )

    return detail_rows, summary_rows, compact_rows


def to_csv(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    headers = list(rows[0].keys())
    out = StringIO()
    writer = csv.DictWriter(out, fieldnames=headers, delimiter=';')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue()


def table_md(rows: list[dict[str, str]], title: str) -> str:
    if not rows:
        return f"## {title}\n\nSin datos.\n"
    headers = list(rows[0].keys())
    lines = [f"## {title}", "", "| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        vals = [str(row[h]).replace("|", "\\|") for h in headers]
        lines.append("| " + " | ".join(vals) + " |")
    lines.append("")
    return "\n".join(lines)


def to_markdown(detail_rows: list[dict[str, str]], summary_rows: list[dict[str, str]], compact_rows: list[dict[str, str]]) -> str:
    lines = [
        "# Comparacion parent outputs vs child params",
        "",
        "Criterio: solo claves presentes en outputs.exports del parent y params.parameters del child.",
        "",
        table_md(compact_rows, "Resumen Compacto por Transicion de Fase"),
        table_md(summary_rows, "Resumen por Variante Hoja y Transicion"),
        table_md(detail_rows, "Detalle por Parametro (Interseccion)"),
    ]
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    detail_rows, summary_rows, compact_rows = compare_edges(root, args.leaf_phase, args.leaf_regex)

    if output.suffix.lower() == ".csv":
        rendered = to_csv(detail_rows)
    else:
        rendered = to_markdown(detail_rows, summary_rows, compact_rows)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered, encoding="utf-8")

    print(f"Salida generada en: {output}")
    print(f"Filas detalle: {len(detail_rows)}")
    print(f"Filas resumen: {len(summary_rows)}")
    print(f"Filas compactas: {len(compact_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())