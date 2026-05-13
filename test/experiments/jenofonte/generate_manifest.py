#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path
from typing import Any

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
VARIANT_RE = re.compile(r"^v(\d{3})$")


def load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"YAML invalido: {path}")
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
        raise ValueError(f"Indice de variante fuera de rango para vNNN: {idx}")
    return f"v{idx:03d}"


def next_variant_start(execution_subdir: str) -> int:
    phase_dir = REPO_ROOT / "executions" / execution_subdir
    if not phase_dir.exists():
        return 1

    max_idx = 0
    for child in phase_dir.iterdir():
        if not child.is_dir():
            continue
        match = VARIANT_RE.match(child.name)
        if not match:
            continue
        max_idx = max(max_idx, int(match.group(1)))
    return max_idx + 1


def existing_variant_indices(execution_subdir: str) -> list[int]:
    phase_dir = REPO_ROOT / "executions" / execution_subdir
    if not phase_dir.exists():
        return []

    indices: list[int] = []
    for child in phase_dir.iterdir():
        if not child.is_dir():
            continue
        match = VARIANT_RE.match(child.name)
        if not match:
            continue
        indices.append(int(match.group(1)))
    return sorted(indices)


def latest_existing_block_start(execution_subdir: str, expected_count: int) -> int:
    indices = existing_variant_indices(execution_subdir)
    if not indices:
        return 1
    if expected_count <= 0:
        return indices[-1]
    if len(indices) < expected_count:
        raise ValueError(
            f"No hay suficientes variantes existentes en {execution_subdir}: "
            f"esperadas {expected_count}, encontradas {len(indices)}"
        )

    tail = indices[-expected_count:]
    for prev, curr in zip(tail, tail[1:]):
        if curr != prev + 1:
            raise ValueError(
                f"Las ultimas {expected_count} variantes en {execution_subdir} no forman "
                f"un bloque contiguo: {tail[0]}..{tail[-1]}"
            )
    return tail[0]


def build_f02_rows(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    variants = cfg["phase2"]["variants"]

    for item in variants:
        rows.append(
            {
                "job_id": f"f02_{item['id']}",
                "phase": "f02",
                "variant": item["id"],
                "parent": cfg["global"].get("event_parent", ""),
                "parent_f02": item["id"],
                "make_target": "variant2",
                "script_target": "script2",
                "strategy": cfg["global"]["event_strategy"],
                "pipeline": "",
                "measure": "",
                "direction": "",
                "ow": "",
                "pw": "",
                "lt": "",
                "dedup": "",
                "seed": "",
            }
        )
    return rows


def build_f03_rows(
    cfg: dict[str, Any],
    f02_rows: list[dict[str, Any]],
    start_idx: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    combos = cfg["phase3"]["base_combinations"]
    strategies = cfg["phase3"]["strategies"]

    idx = start_idx
    for row_f02 in f02_rows:
        parent_f02 = row_f02["variant"]

        for combo in combos:
            for strategy in strategies:
                variant = format_variant(idx)
                rows.append(
                    {
                        "job_id": f"f03_{parent_f02}_{combo['id']}_{strategy}",
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


def build_f04_rows(
    cfg: dict[str, Any],
    f03_rows: list[dict[str, Any]],
    start_idx: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    measures = cfg["phase4"]["measures"]

    idx = start_idx
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


def build_f05_rows(
    cfg: dict[str, Any],
    f04_rows: list[dict[str, Any]],
    start_idx: int,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    pipelines = cfg["phase5"]["pipelines"]
    seeds = cfg.get("global", {}).get("seeds", [""])

    idx = start_idx
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
        choices=["f02", "f03", "f04", "f05", "all"],
        help="Fase a expandir",
    )
    parser.add_argument("--output", required=True, help="Ruta de salida del manifest CSV")
    args = parser.parse_args()

    cfg = load_yaml(Path(args.config))

    f02_rows = build_f02_rows(cfg)
    planned_f03_count = len(cfg["phase3"]["base_combinations"]) * len(cfg["phase3"]["strategies"]) * len(f02_rows)

    if args.phase == "f03":
        f03_parent_start = next_variant_start("f03_windows")
    elif args.phase in {"f04", "f05"}:
        f03_parent_start = latest_existing_block_start("f03_windows", planned_f03_count)
    else:
        f03_parent_start = next_variant_start("f03_windows")

    f03_rows = build_f03_rows(cfg, f02_rows, f03_parent_start)

    planned_f04_count = sum(len((measure_cfg.get("directions") or ["high"])) for measure_cfg in cfg["phase4"]["measures"]) * len(f03_rows)

    if args.phase == "f04":
        f04_start = next_variant_start("f04_targets")
        f04_parent_rows = f03_rows
    elif args.phase == "f05":
        f04_parent_start = latest_existing_block_start("f04_targets", planned_f04_count)
        f04_parent_rows = build_f04_rows(cfg, f03_rows, f04_parent_start)
        f04_start = next_variant_start("f05_modeling")  # placeholder, not used directly
    else:
        f04_start = next_variant_start("f04_targets")
        f04_parent_rows = f03_rows

    if args.phase == "f05":
        f04_rows = f04_parent_rows
    else:
        f04_rows = build_f04_rows(cfg, f04_parent_rows, f04_start)

    f05_rows = build_f05_rows(cfg, f04_rows, next_variant_start("f05_modeling"))

    if args.phase == "f02":
        rows = f02_rows
    elif args.phase == "f03":
        rows = f03_rows
    elif args.phase == "f04":
        rows = f04_rows
    elif args.phase == "f05":
        rows = f05_rows
    else:
        rows = f02_rows + f03_rows + f04_rows + f05_rows

    write_manifest(Path(args.output), rows)
    print(f"Manifest escrito en: {args.output}")
    print(f"F02: {len(f02_rows)}")
    print(f"F03: {len(f03_rows)}")
    print(f"F04: {len(f04_rows)}")
    print(f"F05: {len(f05_rows)}")
    print(f"Total: {len(rows)}")


if __name__ == "__main__":
    main()
