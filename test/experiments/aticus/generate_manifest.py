#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Any

import yaml


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML inválido: {path}")
    return data


def slug(text: str) -> str:
    return (
        text.strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
        .replace("|", "_")
        .replace("=", "")
    )


def format_variant(idx: int) -> str:
    if idx < 0 or idx > 999:
        raise ValueError(f"Índice de variante fuera de rango para vNNN: {idx}")
    return f"v{idx:03d}"


def build_f03_rows(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    combos = cfg["phase3"]["base_combinations"]
    strategies = cfg["phase3"]["strategies"]
    parent_f02 = cfg["phase3"]["parent_f02"]

    idx = 1
    for combo in combos:
        for strategy in strategies:
            variant = format_variant(idx)
            rows.append(
                {
                    "job_id": f"f03_{combo['id']}_{strategy}",
                    "phase": "f03",
                    "variant": variant,
                    "parent": parent_f02,
                    "parent_f02": parent_f02,
                    "make_target": "variant3",
                    "script_target": "script3",
                    "strategy": strategy,
                    "pipeline": "",
                    "measure": "",
                    "direction": "",
                    "ow": combo["ow"],
                    "pw": combo["pw"],
                    "lt": combo["lt"],
                    "dedup": "",
                    "seed": "",
                }
            )
            idx += 1
    return rows

def build_f04_rows(cfg: dict[str, Any], f03_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    measures = cfg["phase4"]["measures"]

    idx = 1
    for row_f03 in f03_rows:
        for measure_cfg in measures:
            measure = measure_cfg["name"]
            directions = measure_cfg.get("directions", ["high"])

            for direction in directions:
                variant = format_variant(idx)
                rows.append(
                    {
                        "job_id": f"{row_f03['job_id']}_{slug(measure)}_{direction}",
                        "phase": "f04",
                        "variant": variant,
                        "parent": row_f03["variant"],
                        "parent_f02": row_f03["parent_f02"],
                        "make_target": "variant4",
                        "script_target": "script4",
                        "strategy": row_f03["strategy"],
                        "pipeline": "",
                        "measure": measure,
                        "direction": direction,
                        "ow": row_f03["ow"],
                        "pw": row_f03["pw"],
                        "lt": row_f03["lt"],
                        "dedup": "",
                        "seed": "",
                    }
                )
                idx += 1
    return rows

def build_f05_rows(cfg: dict[str, Any], f04_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pipelines = cfg["phase5"]["pipelines"]
    seeds = cfg.get("global", {}).get("seeds", [""])

    idx = 1
    for row_f04 in f04_rows:
        parent_strategy = row_f04["strategy"]

        for pipe in pipelines:
            if pipe["strategy"] != parent_strategy:
                continue

            for seed in seeds:
                variant = format_variant(idx)

                seed_suffix = f"_s{seed}" if seed != "" else ""

                rows.append(
                    {
                        "job_id": f"{row_f04['job_id']}_{pipe['id']}{seed_suffix}",
                        "phase": "f05",
                        "variant": variant,
                        "parent": row_f04["variant"],
                        "parent_f02": row_f04["parent_f02"],
                        "make_target": "variant5",
                        "script_target": "script5",
                        "strategy": row_f04["strategy"],
                        "pipeline": pipe["id"],
                        "measure": row_f04["measure"],
                        "direction": row_f04["direction"],
                        "ow": row_f04["ow"],
                        "pw": row_f04["pw"],
                        "lt": row_f04["lt"],
                        "dedup": pipe["dedup"],
                        "seed": seed,
                    }
                )
                idx += 1
    return rows


def write_manifest(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "job_id",
        "phase",
        "variant",
        "parent",
        "parent_f02",
        "make_target",
        "script_target",
        "strategy",
        "pipeline",
        "measure",
        "direction",
        "ow",
        "pw",
        "lt",
        "dedup",
        "seed",
    ]

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True, help="Ruta a experiment.yaml")
    parser.add_argument(
        "--phase",
        required=True,
        choices=["f03", "f04", "f05", "all"],
        help="Fase a expandir",
    )
    parser.add_argument("--output", required=True, help="Ruta de salida del manifest CSV")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))

    f03_rows = build_f03_rows(cfg)
    f04_rows = build_f04_rows(cfg, f03_rows)
    f05_rows = build_f05_rows(cfg, f04_rows)

    if args.phase == "f03":
        rows = f03_rows
    elif args.phase == "f04":
        rows = f04_rows
    elif args.phase == "f05":
        rows = f05_rows
    else:
        rows = f03_rows + f04_rows + f05_rows

    write_manifest(Path(args.output), rows)
    print(f"Manifest escrito en: {args.output}")
    print(f"Filas: {len(rows)}")


if __name__ == "__main__":
    main()

# python test/experiments/aticus/generate_manifest.py --config test/experiments/aticus/experiment.yaml --phase all --output test/experiments/aticus/manifest.csv