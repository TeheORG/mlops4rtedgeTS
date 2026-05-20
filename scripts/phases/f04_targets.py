#!/usr/bin/env python3

import argparse
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from scripts.core.artifacts import (
    sha256_of_file,
    save_outputs_yaml,
    load_params,
    get_variant_dir,
)
from scripts.core.phase_io import load_phase_outputs, resolve_artifact_path
from scripts.core.traceability import validate_outputs


# ============================================================
PHASE = "f04_targets"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
# ============================================================


# ============================================================
# Helper functions
# ============================================================
def _combine_chunks(array):
    if isinstance(array, pa.ChunkedArray):
        return array.combine_chunks()
    return array


def _list_offsets_and_values(list_array):
    list_array = _combine_chunks(list_array)
    offsets = list_array.offsets.to_numpy(zero_copy_only=False)
    values = list_array.values.to_numpy(zero_copy_only=False)
    return offsets, values


def label_prediction_batch(pw_array, threshold_value: float, direction: str) -> np.ndarray:
    offsets, values = _list_offsets_and_values(pw_array)
    n_rows = len(offsets) - 1
    labels = np.zeros(n_rows, dtype=np.int8)

    if values.size == 0 or n_rows == 0:
        return labels

    if direction == "high":
        matches = values > threshold_value
    elif direction == "low":
        matches = values < threshold_value
    else:
        raise ValueError(f"Direccion desconocida: {direction}")

    lengths = np.diff(offsets)
    non_empty = lengths > 0
    if np.any(non_empty):
        starts = offsets[:-1][non_empty]
        labels[non_empty] = np.maximum.reduceat(matches, starts).astype(np.int8)

    return labels


class OWDedupStats:
    def __init__(self):
        self._counts_by_hash = {}
        self.total = 0

    @staticmethod
    def _hash_values(values: np.ndarray, start: int, end: int) -> bytes:
        if start == end:
            return b"EMPTY"
        return hashlib.md5(values[start:end].view(np.uint8)).digest()

    def update(self, ow_array, labels: np.ndarray):
        offsets, values = _list_offsets_and_values(ow_array)

        for row_idx, label in enumerate(labels):
            digest = self._hash_values(values, int(offsets[row_idx]), int(offsets[row_idx + 1]))
            count, positives = self._counts_by_hash.get(digest, (0, 0))
            self._counts_by_hash[digest] = (count + 1, positives + int(label))
            self.total += 1

    def to_dict(self):
        unique_ow = len(self._counts_by_hash)
        num_duplicate_sequences = 0
        ambiguous_sequences = 0
        ambiguous_samples = 0
        consistency_sum = 0.0

        for count, positives in self._counts_by_hash.values():
            if count > 1:
                num_duplicate_sequences += count - 1
            if 0 < positives < count:
                ambiguous_sequences += 1
                ambiguous_samples += count
            consistency_sum += max(positives, count - positives) / count

        total = self.total
        return {
            "total_sequences": int(total),
            "unique_ow_sequences": int(unique_ow),
            "num_duplicate_sequences": int(num_duplicate_sequences),
            "duplicate_ratio": float(num_duplicate_sequences / total if total else 0.0),
            "ambiguous_sequences": int(ambiguous_sequences),
            "ambiguous_samples": int(ambiguous_samples),
            "ambiguous_ratio": float(ambiguous_samples / total if total else 0.0),
            "avg_label_consistency_per_ow": float(
                consistency_sum / unique_ow if unique_ow else 0.0
            ),
        }


def require_float(value, name: str) -> float:
    if value is None:
        raise RuntimeError(f"Falta valor requerido: {name}")
    return float(value)


def require_bool(value, name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    raise ValueError(f"{name} debe ser booleano")


def dedup_stats_from_parent(parent_exports: dict, total: int) -> dict:
    unique_ow = parent_exports.get("n_unique_ow_hash")
    if unique_ow is None:
        dup_ratio = parent_exports.get("dup_ratio_ow")
        if dup_ratio is not None and total:
            unique_ow = round(total * (1.0 - float(dup_ratio)))
        else:
            unique_ow = total

    unique_ow = int(unique_ow)
    num_duplicate_sequences = max(total - unique_ow, 0)
    duplicate_ratio = num_duplicate_sequences / total if total else 0.0

    return {
        "total_sequences": int(total),
        "unique_ow_sequences": int(unique_ow),
        "num_duplicate_sequences": int(num_duplicate_sequences),
        "duplicate_ratio": float(duplicate_ratio),
        "ambiguous_sequences": None,
        "ambiguous_samples": None,
        "ambiguous_ratio": None,
        "avg_label_consistency_per_ow": None,
        "source": "parent_f03",
    }


# ============================================================
# MAIN
# ============================================================
def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant
    variant_dir = get_variant_dir(PHASE, variant)

    params_data = load_params(PHASE, variant)
    params = params_data["parameters"]
    parent_variant = params_data["parent"]

    print(f"\n===== INICIO {PHASE} / {variant} =====")

    start_time = time.perf_counter()

    # --------------------------------------------------------
    # Resolver parent F03
    # --------------------------------------------------------

    parent_phase = "f03_windows"

    parent_outputs, parent_dir = load_phase_outputs(
        PROJECT_ROOT,
        parent_phase,
        parent_variant,
        "F04",
    )

    parent_dataset_path = resolve_artifact_path(
        parent_dir,
        parent_outputs,
        ["dataset"],
        "F04",
    )

    if not parent_dataset_path.exists():
        raise RuntimeError("No existe dataset de ventanas F03")

    parent_parquet = pq.ParquetFile(parent_dataset_path, memory_map=True)
    parent_columns = set(parent_parquet.schema_arrow.names)

    if "OW_values" not in parent_columns or "PW_values" not in parent_columns:
        raise RuntimeError(
            "El dataset F03 debe contener columnas OW_values y PW_values"
        )

    # --------------------------------------------------------
    # Resolver F02 para min/max de la medida
    # --------------------------------------------------------

    parent_exports = parent_outputs.get("exports", {})
    parent_f02 = parent_exports.get("parent_f02")
    if not parent_f02:
        raise RuntimeError("F03 no exporta parent_f02; no se puede resolver F02")

    f02_outputs, _ = load_phase_outputs(
        PROJECT_ROOT,
        "f02_events",
        parent_f02,
        "F04",
    )

    f02_exports = f02_outputs.get("exports", {})
    f02_metrics = f02_outputs.get("metrics", {})

    measure_name = f02_exports.get("measure_name")
    value_col = f02_exports.get("value_col", "value")
    min_value = require_float(f02_metrics.get("min"), "F02 metrics.min")
    max_value = require_float(f02_metrics.get("max"), "F02 metrics.max")

    if measure_name is None:
        raise RuntimeError("F02 no exporta measure_name")
    if max_value < min_value:
        raise RuntimeError(
            f"Rango inválido en F02: min={min_value}, max={max_value}"
        )

    # --------------------------------------------------------
    # Parámetros de objetivo
    # --------------------------------------------------------

    threshold_percentage = float(params["threshold"])
    direction = str(params["direction"]).strip().lower()

    if not 0.0 <= threshold_percentage <= 100.0:
        raise ValueError("threshold debe estar en el rango [0, 100]")
    if direction not in {"high", "low"}:
        raise ValueError("direction debe ser 'high' o 'low'")

    threshold_value = min_value + (threshold_percentage / 100.0) * (max_value - min_value)

    prediction_name = params.get(
        "prediction_name",
        f"{measure_name}_{direction}_{threshold_percentage:g}pct",
    )

    print("[INFO] Objetivo de predicción:")
    print(f"  measure_name          = {measure_name}")
    print(f"  direction             = {direction}")
    print(f"  threshold_percentage  = {threshold_percentage}")
    print(f"  threshold_value       = {threshold_value}")

    # --------------------------------------------------------
    # Etiquetado
    # --------------------------------------------------------

    output_path = variant_dir / "04_targets.parquet"

    schema = pa.schema([
        ("OW_values", pa.list_(pa.float64())),
        ("label", pa.int8()),
    ])

    batch_size = int(params.get("batch_size", 50_000))
    if batch_size <= 0:
        raise ValueError("batch_size debe ser mayor que 0")
    compute_dedup_stats = require_bool(params.get("compute_dedup_stats", False), "compute_dedup_stats")

    total = 0
    positives = 0
    dedup = OWDedupStats() if compute_dedup_stats else None

    writer = pq.ParquetWriter(output_path, schema, compression="snappy")
    try:
        for batch in parent_parquet.iter_batches(
            batch_size=batch_size,
            columns=["OW_values", "PW_values"],
        ):
            ow_array = batch.column(batch.schema.get_field_index("OW_values"))
            pw_array = batch.column(batch.schema.get_field_index("PW_values"))
            labels = label_prediction_batch(pw_array, threshold_value, direction)

            total += len(labels)
            positives += int(labels.sum())
            if dedup is not None:
                dedup.update(ow_array, labels)

            table_out = pa.Table.from_arrays(
                [ow_array, pa.array(labels, type=pa.int8())],
                schema=schema,
            )
            writer.write_table(table_out)
    finally:
        writer.close()

    # --------------------------------------------------------
    # Estadísticas
    # --------------------------------------------------------

    negatives = total - positives
    positive_ratio = positives / total if total else 0.0
    negative_ratio = negatives / total if total else 0.0
    if dedup is not None:
        dedup_stats = dedup.to_dict()
        dedup_stats["source"] = "f04_streaming_hash"
    else:
        dedup_stats = dedup_stats_from_parent(parent_exports, total)

    elapsed = time.perf_counter() - start_time

    print(f"[INFO] Total ventanas: {total}")
    print(f"[INFO] Positivas: {positives}")
    print(f"[INFO] Negativas: {negatives}")
    print(f"[INFO] Positive ratio: {positive_ratio:.6f}")

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    report_path = variant_dir / "04_targets_report.html"
    report_path.write_text(
        f"""
        <html>
        <body>
        <h1>F04 Targets — {variant}</h1>
        <p>Parent F03: {parent_variant}</p>
        <p>Parent F02: {parent_f02}</p>
        <p>Prediction name: {prediction_name}</p>
        <p>Measure: {measure_name}</p>
        <p>Value column: {value_col}</p>
        <p>Direction: {direction}</p>
        <p>Threshold percentage: {threshold_percentage:.6f}</p>
        <p>Threshold value: {threshold_value:.12g}</p>
        <p>Min value: {min_value:.12g}</p>
        <p>Max value: {max_value:.12g}</p>
        <p>Total windows: {total}</p>
        <p>Positives: {positives}</p>
        <p>Negatives: {negatives}</p>
        <p>Positive ratio: {positive_ratio:.6f}</p>
        <p>Negative ratio: {negative_ratio:.6f}</p>
        </body>
        </html>
        """,
        encoding="utf-8",
    )

    # --------------------------------------------------------
    # outputs.yaml
    # --------------------------------------------------------

    window_strategy = parent_exports.get("window_strategy")
    dup_ratio_ow = parent_exports.get("dup_ratio_ow")
    dup_ratio_pw = parent_exports.get("dup_ratio_pw")
    seq_len_mean_ow = parent_exports.get("seq_len_mean_ow")

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": {
            "dataset": {
                "path": output_path.name,
                "sha256": sha256_of_file(output_path),
            },
            "report": {
                "path": report_path.name,
                "sha256": sha256_of_file(report_path),
            },
        },
        "exports": {
            "Tu": parent_exports.get("Tu", params.get("Tu")),
            "OW": parent_exports.get("OW", params.get("OW")),
            "LT": parent_exports.get("LT", params.get("LT")),
            "PW": parent_exports.get("PW", params.get("PW")),
            "prediction_name": prediction_name,
            "measure_name": measure_name,
            "value_col": value_col,
            "direction": direction,
            "threshold_percentage": float(threshold_percentage),
            "threshold_value": float(threshold_value),
            "min_value": float(min_value),
            "max_value": float(max_value),
            "window_strategy": window_strategy,
            "parent_f03": parent_variant,
            "parent_f02": parent_f02,
            "n_windows": int(total),
            "n_windows_pos": int(positives),
            "n_windows_neg": int(negatives),
            "positive_ratio": float(positive_ratio),
            "negative_ratio": float(negative_ratio),
            "class_balance_ratio": float(positive_ratio),
            "deduplication_stats": dedup_stats,
            "unique_ratio": dedup_stats["unique_ow_sequences"] / total if total else 0.0,
            "dup_ratio_ow_parent": dup_ratio_ow,
            "dup_ratio_pw_parent": dup_ratio_pw,
            "seq_len_mean_ow_parent": seq_len_mean_ow,
        },
        "metrics": {
            "execution_time": float(elapsed),
            "positive_ratio": float(positive_ratio),
            "negative_ratio": float(negative_ratio),
            "n_windows": int(total),
            "n_windows_pos": int(positives),
            "n_windows_neg": int(negatives),
            "threshold_value": float(threshold_value),
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)

    print(f"\n===== FASE {PHASE} COMPLETADA =====")


if __name__ == "__main__":
    main()
