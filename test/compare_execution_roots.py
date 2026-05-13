#!/usr/bin/env python3
"""Compara variantes entre dos árboles de ejecuciones y genera una tabla Markdown.

Uso típico:
  python test/compare_execution_roots.py \
    --left executions \
    --right executions-linux \
    --left-label macOS \
    --right-label Linux \
    --output test/executions_macos_vs_linux.md
"""

from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path
from typing import Any

import yaml


PHASE_METRIC_PRIORITY: dict[str, list[str]] = {
    "f01_explore": ["n_rows", "n_columns", "n_nan_detected", "nan_ratio"],
    "f02_events": ["n_events", "n_types", "n_rows_in", "n_rows_out"],
    "f03_windows": ["n_windows", "n_windows_pos", "n_windows_neg", "positive_ratio"],
    "f04_targets": ["n_windows", "n_windows_pos", "n_windows_neg", "positive_ratio"],
    "f05_modeling": [
        "trainable",
        "decision_threshold",
        "best_val_recall",
        "test_precision",
        "test_recall",
        "test_f1",
        "tp",
        "tn",
        "fp",
        "fn",
    ],
    "f06_quant": [
        "edge_capable",
        "decision_threshold",
        "model_size_bytes",
        "arena_estimated_bytes",
        "footprint_estimated_bytes",
        "tflm_compatible",
        "operators_detected",
        "unsupported_operators",
    ],
    "f07_modval": [
        "edge_capable",
        "ok_rate",
        "infer_mean_ms",
        "infer_worst_ms",
        "accuracy",
        "precision",
        "recall",
        "f1",
        "n_inferences",
        "n_ok",
        "n_fail",
    ],
    "f08_sysval": [
        "system_viable",
        "system_quality_score",
        "mean_model_quality_score",
        "ok_rate",
        "sys_cycle_mean_ms",
        "sys_cycle_worst_ms",
        "watchdog_rate",
        "offload_rate",
    ],
}

NON_SIGNIFICANT_KEYS_BY_PHASE: dict[str, set[str]] = {
    "f05_modeling": {"decision_threshold"},
    "f06_quant": {"decision_threshold"},
    "f07_modval": {"infer_mean_ms", "infer_worst_ms", "n_inferences", "n_ok"},
    "f08_sysval": {"sys_cycle_mean_ms", "sys_cycle_worst_ms", "ok_rate"},
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compara variantes entre dos carpetas de ejecuciones y genera una tabla Markdown."
    )
    parser.add_argument("--left", required=True, help="Carpeta de ejecuciones de referencia.")
    parser.add_argument("--right", required=True, help="Segunda carpeta de ejecuciones a comparar.")
    parser.add_argument("--left-label", default="left", help="Etiqueta de la primera columna de resultados.")
    parser.add_argument("--right-label", default="right", help="Etiqueta de la segunda columna de resultados.")
    parser.add_argument(
        "--output",
        required=True,
        help="Ruta del archivo Markdown de salida.",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=1e-3,
        help="Tolerancia relativa para marcar métricas numéricas como compatibles.",
    )
    return parser.parse_args()


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}


def list_phase_dirs(executions_root: Path) -> list[Path]:
    return sorted(
        [path for path in executions_root.iterdir() if path.is_dir() and path.name.startswith("f")],
        key=lambda path: path.name,
    )


def list_variant_dirs(phase_dir: Path) -> list[Path]:
    return sorted(
        [path for path in phase_dir.iterdir() if path.is_dir() and path.name.startswith("v")],
        key=lambda path: path.name,
    )


def fmt_num(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        if abs(value) >= 1000 or (abs(value) < 1e-3 and value != 0):
            return f"{value:.6g}"
        return f"{value:.6f}".rstrip("0").rstrip(".")
    if value is None:
        return "-"
    if isinstance(value, list):
        preview = ", ".join(str(item) for item in value[:4])
        if len(value) > 4:
            preview += ", ..."
        return f"[{preview}]"
    return str(value)


def fmt_mapping(mapping: dict[str, Any]) -> str:
    if not mapping:
        return "-"
    return "<br>".join(f"{key}={fmt_num(value)}" for key, value in mapping.items())


def read_csv_first_row(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        row = next(reader, None)
    if row is None:
        return {}

    parsed: dict[str, Any] = {}
    for key, value in row.items():
        if value in (None, ""):
            continue
        try:
            number = float(value)
        except ValueError:
            parsed[key] = value
            continue
        if number.is_integer():
            parsed[key] = int(number)
        else:
            parsed[key] = number
    return parsed


def summarize_variant(phase_name: str, variant_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    outputs = load_yaml(variant_dir / "outputs.yaml")
    params = load_yaml(variant_dir / "params.yaml")

    merged: dict[str, Any] = {}
    for section in ("exports", "metrics"):
        section_value = outputs.get(section)
        if isinstance(section_value, dict):
            merged.update(section_value)

    if phase_name == "f07_modval":
        merged.update(read_csv_first_row(variant_dir / "metrics_models.csv"))

    if phase_name == "f08_sysval":
        selection = load_yaml(variant_dir / "08_selected_configuration.yaml")
        for key in ("system_viable", "configuration_edge_capable", "compatible_input_signature"):
            if key in selection:
                merged[key] = selection[key]
        merged.update(load_yaml(variant_dir / "metrics_system_summary.yaml"))

    metric_keys = PHASE_METRIC_PRIORITY.get(phase_name, [])
    summary = {key: merged.get(key) for key in metric_keys if key in merged}

    # Regla solicitada: en F08, si no es viable, no mostrar más detalle en la celda.
    if phase_name == "f08_sysval" and summary.get("system_viable") is False:
        summary = {"system_viable": False}

    parameters = params.get("parameters")
    if not isinstance(parameters, dict):
        parameters = {}

    # Limpieza solicitada para mantener columnas compactas y comparables.
    if phase_name == "f05_modeling":
        parameters.pop("automl", None)
        parameters.pop("search_space", None)
    elif phase_name == "f06_quant":
        parameters.pop("eedu", None)
        parameters.pop("thresholding", None)

    return parameters, summary


def compare_metrics(
    phase_name: str,
    left: dict[str, Any],
    right: dict[str, Any],
    tolerance: float,
) -> tuple[str, str]:
    if not left or not right:
        return "sin datos", "sin datos"

    exact = True
    differing_keys: list[str] = []

    for key in sorted(set(left) | set(right)):
        left_value = left.get(key)
        right_value = right.get(key)

        if left_value == right_value:
            continue

        exact = False
        if (
            isinstance(left_value, (int, float))
            and isinstance(right_value, (int, float))
            and not isinstance(left_value, bool)
            and not isinstance(right_value, bool)
        ):
            scale = max(1.0, abs(float(left_value)), abs(float(right_value)))
            rel_diff = abs(float(left_value) - float(right_value)) / scale
            if rel_diff <= tolerance:
                continue

        differing_keys.append(key)

    if exact:
        return "iguales", "sin diferencias"
    if not differing_keys:
        return "compatibles", "solo diferencias numéricas dentro de tolerancia"

    non_significant_keys = NON_SIGNIFICANT_KEYS_BY_PHASE.get(phase_name, set())
    significant = [key for key in differing_keys if key not in non_significant_keys]
    non_significant = [key for key in differing_keys if key in non_significant_keys]

    if significant:
        preview = ", ".join(significant[:3])
        if len(significant) > 3:
            preview += ", ..."
        status = f"distintos ({preview})"
    else:
        status = "compatibles (solo no significativas)"

    sig_text = ", ".join(significant) if significant else "-"
    non_sig_text = ", ".join(non_significant) if non_significant else "-"
    analysis = f"significativas: {sig_text}; no_significativas: {non_sig_text}"
    return status, analysis


def build_rows(
    left_root: Path,
    right_root: Path,
    tolerance: float,
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []

    for left_phase_dir in list_phase_dirs(left_root):
        phase_name = left_phase_dir.name
        right_phase_dir = right_root / phase_name
        if not right_phase_dir.exists():
            continue

        right_variants = {path.name for path in list_variant_dirs(right_phase_dir)}
        for left_variant_dir in list_variant_dirs(left_phase_dir):
            variant_name = left_variant_dir.name
            if variant_name not in right_variants:
                continue

            right_variant_dir = right_phase_dir / variant_name
            left_params, left_metrics = summarize_variant(phase_name, left_variant_dir)
            right_params, right_metrics = summarize_variant(phase_name, right_variant_dir)

            params_text = fmt_mapping(left_params)
            if left_params != right_params and phase_name != "f07_modval":
                right_only = {
                    key: value
                    for key, value in right_params.items()
                    if left_params.get(key) != value
                }
                if right_only:
                    delta_text = "; ".join(f"{key}={fmt_num(value)}" for key, value in right_only.items())
                    params_text = f"{params_text}<br>right_delta: {delta_text}" if params_text != "-" else f"right_delta: {delta_text}"

            comparison, significance = compare_metrics(
                phase_name,
                left_metrics,
                right_metrics,
                tolerance,
            )

            rows.append(
                {
                    "phase": phase_name,
                    "variant": variant_name,
                    "params": params_text,
                    "left": fmt_mapping(left_metrics),
                    "right": fmt_mapping(right_metrics),
                    "comparison": comparison,
                    "significance": significance,
                }
            )

    return rows


def escape_cell(value: str) -> str:
    return value.replace("|", "\\|")


def render_markdown(
    rows: list[dict[str, str]],
    left_label: str,
    right_label: str,
    tolerance: float,
) -> str:
    lines = [
        "# Comparativa de variantes entre dos árboles de ejecuciones",
        "",
        (
            "Criterio de compatibilidad: `iguales` si todas las métricas extraídas coinciden "
            "exactamente; `compatibles` si solo difieren en valores numéricos dentro de una "
            f"tolerancia relativa de {tolerance}; `distintos` en el resto de casos."
        ),
        "",
        f"Filas comparadas: {len(rows)}",
        "",
        (
            f"| fase | varianteid | parámetros make variant | {left_label}: resultados principales | "
            f"{right_label}: resultados principales | comparación | análisis de diferencias |"
        ),
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]

    for row in rows:
        lines.append(
            "| {phase} | {variant} | {params} | {left} | {right} | {comparison} | {significance} |".format(
                phase=escape_cell(row["phase"]),
                variant=escape_cell(row["variant"]),
                params=escape_cell(row["params"]),
                left=escape_cell(row["left"]),
                right=escape_cell(row["right"]),
                comparison=escape_cell(row["comparison"]),
                significance=escape_cell(row["significance"]),
            )
        )

    return "\n".join(lines) + "\n"


def render_csv(rows: list[dict[str, str]], left_label: str, right_label: str) -> str:
    fieldnames = [
        "fase",
        "varianteid",
        "parametros_make_variant",
        f"{left_label}_resultados_principales",
        f"{right_label}_resultados_principales",
        "comparacion",
        "analisis_diferencias",
    ]

    output_lines: list[str] = []
    from io import StringIO

    buffer = StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "fase": row["phase"],
                "varianteid": row["variant"],
                "parametros_make_variant": row["params"].replace("<br>", "; "),
                f"{left_label}_resultados_principales": row["left"].replace("<br>", "; "),
                f"{right_label}_resultados_principales": row["right"].replace("<br>", "; "),
                "comparacion": row["comparison"],
                "analisis_diferencias": row["significance"],
            }
        )
    return buffer.getvalue()


def main() -> int:
    args = parse_args()
    left_root = Path(args.left).resolve()
    right_root = Path(args.right).resolve()
    output_path = Path(args.output).resolve()

    rows = build_rows(left_root, right_root, args.tolerance)
    output_suffix = output_path.suffix.lower()
    if output_suffix == ".csv":
        rendered = render_csv(rows, args.left_label, args.right_label)
    else:
        rendered = render_markdown(rows, args.left_label, args.right_label, args.tolerance)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(rendered, encoding="utf-8")

    print(f"Tabla generada en: {output_path}")
    print(f"Filas comparadas: {len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())