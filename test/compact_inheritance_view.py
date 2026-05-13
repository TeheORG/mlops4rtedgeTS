#!/usr/bin/env python3
"""Construye una vista compacta del efecto de la herencia de parámetros.

Entrada esperada: CSV generado por test/trace_lineage_params.py.
Salida: Markdown con tablas compactas + figura Mermaid, y CSV resumen opcional.
"""

from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Genera una vista compacta de herencia de parámetros.")
    parser.add_argument("--input", required=True, help="CSV de entrada (v70_lineage_params.csv).")
    parser.add_argument("--output-md", required=True, help="Ruta del informe Markdown compacto.")
    parser.add_argument("--output-csv", required=False, help="Ruta CSV compacta opcional.")
    return parser.parse_args()


def parse_status(inheritance_cell: str) -> str:
    # Formato esperado: "status; cambios_en=..."
    return inheritance_cell.split(";", 1)[0].strip() if inheritance_cell else "desconocido"


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        return [dict(row) for row in reader]


def build_compact_views(rows: list[dict[str, str]]):
    by_param: dict[str, dict[str, object]] = {}
    by_origin_phase: dict[str, Counter[str]] = defaultdict(Counter)
    global_status = Counter()

    variants = sorted({row["leaf_variant"] for row in rows})
    total_variants = len(variants)

    for row in rows:
        param = row["parameter"]
        leaf_variant = row["leaf_variant"]
        origin_phase = row["origin_phase"]
        status = parse_status(row["inheritance"])
        leaf_present = row["leaf_value"] != "-"

        global_status[status] += 1
        by_origin_phase[origin_phase][status] += 1

        if param not in by_param:
            by_param[param] = {
                "origin_phases": Counter(),
                "variants": set(),
                "leaf_present": 0,
                "status": Counter(),
            }

        param_row = by_param[param]
        param_row["origin_phases"][origin_phase] += 1
        param_row["variants"].add(leaf_variant)
        if leaf_present:
            param_row["leaf_present"] += 1
        param_row["status"][status] += 1

    compact_param_rows: list[dict[str, str]] = []
    for param in sorted(by_param):
        data = by_param[param]
        top_origin_phase, _ = data["origin_phases"].most_common(1)[0]
        present_in = len(data["variants"])
        leaf_present = int(data["leaf_present"])
        status_counter: Counter[str] = data["status"]

        compact_param_rows.append(
            {
                "parameter": param,
                "fase_origen_dominante": top_origin_phase,
                "presente_en_variantes": f"{present_in}/{total_variants}",
                "presente_en_hoja": str(leaf_present),
                "heredado_sin_cambios": str(status_counter.get("heredado_sin_cambios", 0)),
                "redefinido_en_linaje": str(status_counter.get("redefinido_en_linaje", 0)),
                "generado_en_hoja": str(status_counter.get("generado_en_hoja", 0)),
                "solo_ancestro": str(status_counter.get("solo_ancestro", 0)),
            }
        )

    compact_phase_rows: list[dict[str, str]] = []
    for phase in sorted(by_origin_phase):
        counter = by_origin_phase[phase]
        total = sum(counter.values())
        compact_phase_rows.append(
            {
                "fase_origen": phase,
                "total_filas": str(total),
                "heredado_sin_cambios": str(counter.get("heredado_sin_cambios", 0)),
                "redefinido_en_linaje": str(counter.get("redefinido_en_linaje", 0)),
                "generado_en_hoja": str(counter.get("generado_en_hoja", 0)),
                "solo_ancestro": str(counter.get("solo_ancestro", 0)),
            }
        )

    return compact_param_rows, compact_phase_rows, global_status


def render_table_md(rows: list[dict[str, str]], title: str) -> str:
    if not rows:
        return f"## {title}\n\nSin datos.\n"

    headers = list(rows[0].keys())
    lines = [f"## {title}", ""]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for row in rows:
        cells = [str(row[h]).replace("|", "\\|") for h in headers]
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    return "\n".join(lines)


def render_mermaid_pie(global_status: Counter[str]) -> str:
    if not global_status:
        return "Sin datos para figura Mermaid."

    lines = ["```mermaid", "pie title Distribucion global del estado de herencia"]
    for key, value in global_status.items():
        lines.append(f'    "{key}" : {value}')
    lines.append("```")
    return "\n".join(lines)


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), delimiter=";")
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    input_path = Path(args.input).resolve()
    output_md = Path(args.output_md).resolve()
    output_csv = Path(args.output_csv).resolve() if args.output_csv else None

    rows = load_rows(input_path)
    compact_param_rows, compact_phase_rows, global_status = build_compact_views(rows)

    content = [
        "# Vista Compacta del Efecto de la Herencia",
        "",
        f"Filas base analizadas: {len(rows)}",
        "",
        render_table_md(compact_phase_rows, "Efecto por Fase de Origen"),
        render_table_md(compact_param_rows, "Efecto por Parametro"),
        "## Figura Compacta",
        "",
        render_mermaid_pie(global_status),
        "",
    ]

    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text("\n".join(content), encoding="utf-8")

    if output_csv:
        output_csv.parent.mkdir(parents=True, exist_ok=True)
        write_csv(output_csv, compact_param_rows)

    print(f"Informe compacto generado en: {output_md}")
    if output_csv:
        print(f"CSV compacto generado en: {output_csv}")
    print(f"Parametros unicos: {len(compact_param_rows)}")
    print(f"Fases de origen: {len(compact_phase_rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())