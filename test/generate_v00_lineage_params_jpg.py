#!/usr/bin/env python3
"""Genera un JPG del linaje v?00 (fases 1-7) con parametros creados por variante.

Reglas implementadas:
  - Solo fases f01..f07.
  - Solo variantes v100 -> v700.
  - Bajo cada variante se listan unicamente los parametros cuyo primer origen
    en el linaje ocurre en esa variante.
"""

from __future__ import annotations

import argparse
import json
import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch
import yaml


CHAIN = [
    ("f01_explore", "v100"),
    ("f02_events", "v200"),
    ("f03_windows", "v300"),
    ("f04_targets", "v400"),
    ("f05_modeling", "v500"),
    ("f06_quant", "v600"),
    ("f07_modval", "v700"),
]

TARGET_PARAMS: dict[str, list[str]] = {
    "Tu": ["Tu"],
    # Unificado con el nombre de F02 (v2): n_types.
    "n_types": ["n_types", "num_events_types", "event_types_max", "event_type_count"],
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
    "arena_estimada_bytes": ["arena_estimada_bytes", "arena_estimated_bytes", "required_arena_bytes", "arena_bytes"],
    "footprint_estimated_bytes": ["footprint_estimated_bytes"],
    "operators": ["operators", "operators_union"],
    "quality_score": ["quality_score", "system_quality_score", "mean_model_quality_score"],
    "itmax_ms": ["itmax_ms", "MTI_MS", "max_exec_time_ms"],
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera JPG de linaje v?00 con parametros por variante de creacion.")
    parser.add_argument("--root", default="executions", help="Carpeta base de ejecuciones.")
    parser.add_argument("--output", default="test/v00_lineage_params.jpg", help="Ruta JPG de salida.")
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


def fmt_value(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return f"{value:.4f}"
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


def build_nodes(root: Path) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    for phase, variant in CHAIN:
        base = root / phase / variant
        params_yaml = load_yaml(base / "params.yaml")
        outputs_yaml = load_yaml(base / "outputs.yaml")

        params = params_yaml.get("parameters") if isinstance(params_yaml.get("parameters"), dict) else {}
        exports = outputs_yaml.get("exports") if isinstance(outputs_yaml.get("exports"), dict) else {}

        nodes.append(
            {
                "phase": phase,
                "variant": variant,
                "params": flatten_mapping(params),
                "exports": flatten_mapping(exports),
            }
        )
    return nodes


def find_created_params(nodes: list[dict[str, Any]]) -> dict[str, list[str]]:
    created_by_variant: dict[str, list[str]] = {node["variant"]: [] for node in nodes}

    for canonical, aliases in TARGET_PARAMS.items():
        found = None
        for node in nodes:
            for alias in aliases:
                if alias in node["params"]:
                    found = (node["variant"], alias, node["params"][alias])
                    break
            if found is not None:
                break
            for alias in aliases:
                if alias in node["exports"]:
                    found = (node["variant"], alias, node["exports"][alias])
                    break
            if found is not None:
                break

        if found is None:
            continue

        variant, _, value = found
        created_by_variant[variant].append(f"{canonical}: {fmt_value(value)}")

    for variant in created_by_variant:
        created_by_variant[variant].sort()
    return created_by_variant


def draw_chart(nodes: list[dict[str, Any]], created: dict[str, list[str]], output: Path) -> None:
    # Estilo/medidas base copiados del render JPG de generate_variants_diagram.py.
    compact_layout = True
    phase_step = 1.05 if compact_layout else 1.45
    node_w = 0.60 if compact_layout else 0.92
    # Caja superior de variante más baja que en la prueba anterior.
    node_h = 0.26 if compact_layout else 0.95
    top_y = 0.0

    x_positions = [i * phase_step for i in range(len(nodes))]

    # Prepara textos envueltos y altura dinámica de la caja blanca inferior.
    wrapped_by_variant: dict[str, list[str]] = {}
    lower_heights: dict[str, float] = {}
    for node in nodes:
        variant = node["variant"]
        lines = created.get(variant, [])
        if not lines:
            wrapped_lines = ["(sin parametros nuevos del listado)"]
        else:
            wrapped_lines = []
            for line in lines:
                wrapped_lines.extend(textwrap.wrap(line, width=24) or [line])
        wrapped_by_variant[variant] = wrapped_lines
        base_h = 0.16
        per_line = 0.056
        lower_heights[variant] = max(base_h, base_h + per_line * len(wrapped_lines))

    # Determina límites de figura con margen para cajas inferiores.
    x_min = -0.8
    x_max = (x_positions[-1] if x_positions else 0.0) + 0.8
    min_lower_y = min(top_y - node_h / 2 - 0.10 - lower_heights[n["variant"]] for n in nodes)
    y_min = min_lower_y - 0.30
    y_max = top_y + node_h / 2 + 0.9

    fig_w = max(12.0 if compact_layout else 18.0, (x_max - x_min) * (1.7 if compact_layout else 2.2))
    fig_h = max(5.8 if compact_layout else 8.0, (y_max - y_min) * (1.0 if compact_layout else 1.2) + (1.2 if compact_layout else 2.0))
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    # Flechas de linaje (mismo estilo que generate_variants_diagram.py).
    for i in range(len(nodes) - 1):
        sx = x_positions[i]
        tx = x_positions[i + 1]
        start = (sx + node_w / 2, top_y)
        end = (tx - node_w / 2, top_y)
        arrow = FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=9,
            linewidth=0.8,
            color="#000000",
            alpha=0.8,
        )
        ax.add_patch(arrow)

    for i, node in enumerate(nodes):
        variant = node["variant"]
        x = x_positions[i]

        # Caja superior gris (idéntica en estilo/medida al linaje JPG existente).
        top_box = FancyBboxPatch(
            (x - node_w / 2, top_y - node_h / 2),
            node_w,
            node_h,
            boxstyle="round,pad=0.03,rounding_size=0.03",
            facecolor="#f1f3f4",
            edgecolor="#666666",
            linewidth=0.9,
        )
        ax.add_patch(top_box)

        ax.text(
            x,
            top_y + node_h / 2 - 0.05,
            variant,
            ha="center",
            va="top",
            fontsize=7.4 if compact_layout else 8.7,
            fontweight="bold",
        )

        # Caja inferior blanca, misma anchura y altura dinámica si hace falta.
        lower_h = lower_heights[variant]
        lower_top = top_y - node_h / 2 - 0.10
        lower_y0 = lower_top - lower_h
        lower_box = FancyBboxPatch(
            (x - node_w / 2, lower_y0),
            node_w,
            lower_h,
            boxstyle="round,pad=0.03,rounding_size=0.03",
            facecolor="#ffffff",
            edgecolor="#d7d7d7",
            linewidth=0.45,
        )
        ax.add_patch(lower_box)

        ax.text(
            x - node_w / 2 + 0.03,
            lower_top - 0.03,
            "\n".join(wrapped_by_variant[variant]),
            ha="left",
            va="top",
            fontsize=5.8 if compact_layout else 6.5,
            family="monospace",
        )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, y_max)
    ax.axis("off")

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=max(120, 220), format="jpg", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    nodes = build_nodes(root)
    created = find_created_params(nodes)
    draw_chart(nodes, created, output)

    print(f"JPG generado en: {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())