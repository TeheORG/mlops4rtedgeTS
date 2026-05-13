#!/usr/bin/env python3
"""Compara dos linajes paralelos de variantes dentro del mismo árbol de ejecuciones.

Uso típico:
  python test/compare_lineage_variants.py \
    --root executions \
    --output test/executions_vf0_vs_vf1.md

Convención soportada por defecto:
  - linaje base: vP0N
  - linaje paralelo: vP1N

La comparación de parámetros normaliza referencias a variantes del linaje paralelo
para llevarlas a su equivalente del linaje base. Así se puede comprobar si dos
variantes con parents equivalentes y mismos parámetros producen los mismos resultados.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path
from typing import Any

from compare_execution_roots import (
    compare_metrics,
    escape_cell,
    fmt_mapping,
    list_phase_dirs,
    render_csv,
    render_markdown,
    summarize_variant,
)


VARIANT_PATTERN = re.compile(r"^v([1-8])([0-9])([0-9])$")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara dos linajes paralelos de variantes dentro de una carpeta executions."
    )
    parser.add_argument("--root", required=True, help="Carpeta base de ejecuciones.")
    parser.add_argument(
        "--base-family",
        default="0",
        help="Dígito de familia para el linaje base dentro de vP?N. Por defecto: 0.",
    )
    parser.add_argument(
        "--parallel-family",
        default="1",
        help="Dígito de familia para el linaje paralelo dentro de vP?N. Por defecto: 1.",
    )
    parser.add_argument(
        "--base-label",
        default="vf0",
        help="Etiqueta para la columna de resultados del linaje base.",
    )
    parser.add_argument(
        "--parallel-label",
        default="vf1",
        help="Etiqueta para la columna de resultados del linaje paralelo.",
    )
    parser.add_argument("--output", required=True, help="Ruta del informe de salida (.md o .csv).")
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-3,
        help="Tolerancia relativa para marcar métricas numéricas como compatibles.",
    )
    return parser.parse_args()


def convert_family(variant: str, family_digit: str) -> str:
    match = VARIANT_PATTERN.match(variant)
    if not match:
        return variant
    phase_digit, _, unit_digit = match.groups()
    return f"v{phase_digit}{family_digit}{unit_digit}"


def normalize_variant_refs(value: Any, source_family: str, target_family: str) -> Any:
    if isinstance(value, dict):
        return {
            key: normalize_variant_refs(item, source_family, target_family)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [normalize_variant_refs(item, source_family, target_family) for item in value]
    if isinstance(value, str):
        match = VARIANT_PATTERN.match(value)
        if match and match.group(2) == source_family:
            return convert_family(value, target_family)
    return value


def compare_parameters(
    left_params: dict[str, Any],
    right_params: dict[str, Any],
    base_family: str,
    parallel_family: str,
) -> tuple[str, str, str]:
    normalized_right = normalize_variant_refs(right_params, parallel_family, base_family)

    left_text = fmt_mapping(left_params)
    right_text = fmt_mapping(right_params)

    if left_params == normalized_right:
        return left_text, right_text, "equivalentes"

    differing_keys = sorted(set(left_params) | set(normalized_right))
    differing_keys = [key for key in differing_keys if left_params.get(key) != normalized_right.get(key)]
    detail = ", ".join(differing_keys) if differing_keys else "-"
    return left_text, right_text, f"distintos ({detail})"


def build_rows(
    root: Path,
    base_family: str,
    parallel_family: str,
    tolerance: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for phase_dir in list_phase_dirs(root):
        phase_name = phase_dir.name
        variants = {path.name: path for path in phase_dir.iterdir() if path.is_dir() and path.name.startswith("v")}

        for variant_name, left_variant_dir in sorted(variants.items()):
            match = VARIANT_PATTERN.match(variant_name)
            if not match or match.group(2) != base_family:
                continue

            parallel_variant = convert_family(variant_name, parallel_family)
            right_variant_dir = variants.get(parallel_variant)
            if right_variant_dir is None:
                continue

            left_params, left_metrics = summarize_variant(phase_name, left_variant_dir)
            right_params, right_metrics = summarize_variant(phase_name, right_variant_dir)

            # Comparar parámetros (solo una celda)
            _, _, params_comparison = compare_parameters(
                left_params,
                right_params,
                base_family,
                parallel_family,
            )

            # Comparar métricas: iguales, diferentes solo en vf0, diferentes solo en vf1
            iguales = []
            solo_vf0 = []
            solo_vf1 = []
            all_keys = set(left_metrics.keys()) | set(right_metrics.keys())
            for k in sorted(all_keys):
                v0 = left_metrics.get(k)
                v1 = right_metrics.get(k)
                if v0 == v1:
                    iguales.append(f"{k}={v0}")
                elif v0 is not None and v1 is not None:
                    solo_vf0.append(f"{k}={v0}")
                    solo_vf1.append(f"{k}={v1}")
                elif v0 is not None:
                    solo_vf0.append(f"{k}={v0}")
                elif v1 is not None:
                    solo_vf1.append(f"{k}={v1}")

            rows.append({
                "vf0": variant_name,
                "vf1": parallel_variant,
                "params": params_comparison,
                "iguales": ",".join(iguales),
                "solo_vf0": ",".join(solo_vf0),
                "solo_vf1": ",".join(solo_vf1),
            })

    return rows


def render_lineage_markdown(
    rows: list[dict[str, str]],
    base_label: str,
    parallel_label: str,
    tolerance: float,
) -> str:
    lines = [
        "# Comparativa entre linajes paralelos de variantes",
        "",
        (
            "La comparación de parámetros normaliza las referencias del linaje paralelo "
            "para mapear sus parents al linaje base equivalente antes de decidir si son iguales."
        ),
        "",
        (
            "Criterio de compatibilidad de resultados: `iguales` si todas las métricas extraídas coinciden "
            "exactamente; `compatibles` si solo difieren en valores numéricos dentro de una "
            f"tolerancia relativa de {tolerance}; `distintos` en el resto de casos."
        ),
        "",
        f"Filas comparadas: {len(rows)}",
        "",
        (
            f"| fase | variante {base_label} | variante {parallel_label} | parámetros {base_label} | "
            f"parámetros {parallel_label} | comparación parámetros | resultados {base_label} | "
            f"resultados {parallel_label} | comparación resultados | análisis de diferencias |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        lines.append(
            "| {phase} | {variant_base} | {variant_parallel} | {base_params} | {parallel_params} | {params_comparison} | {base} | {parallel} | {comparison} | {significance} |".format(
                phase=escape_cell(row["phase"]),
                variant_base=escape_cell(row["variant_base"]),
                variant_parallel=escape_cell(row["variant_parallel"]),
                base_params=escape_cell(row["base_params"]),
                parallel_params=escape_cell(row["parallel_params"]),
                params_comparison=escape_cell(row["params_comparison"]),
                base=escape_cell(row["base"]),
                parallel=escape_cell(row["parallel"]),
                comparison=escape_cell(row["comparison"]),
                significance=escape_cell(row["significance"]),
            )
        )

    return "\n".join(lines) + "\n"


def render_lineage_csv(rows: list[dict[str, str]], base_label: str, parallel_label: str) -> str:
    converted_rows = []
    for row in rows:
        converted_rows.append(
            {
                "phase": row["phase"],
                "variant": f"{row['variant_base']}->{row['variant_parallel']}",
                "params": (
                    f"{base_label}: {row['base_params'].replace('<br>', '; ')} || "
                    f"{parallel_label}: {row['parallel_params'].replace('<br>', '; ')} || "
                    f"params: {row['params_comparison']}"
                ),
                "left": row["base"],
                "right": row["parallel"],
                "comparison": row["comparison"],
                "significance": row["significance"],
            }
        )
    return render_csv(converted_rows, base_label, parallel_label)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output_path = Path(args.output).resolve()

    rows = build_rows(root, args.base_family, args.parallel_family, args.tolerance)
    output_suffix = output_path.suffix.lower()
    # Siempre CSV personalizado con ; como separador
    header = ["vf0", "vf1", "params", "iguales", "solo_vf0", "solo_vf1"]
    lines = [";".join(header)]
    for row in rows:
        line = ";".join([row[h] for h in header])
        lines.append(line)
    rendered = "\n".join(lines) + "\n"

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"Tabla generada en: {output_path}")
    print(f"Filas comparadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())