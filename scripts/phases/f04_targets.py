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
MIN_POSITIVE_RATIO_FOR_TARGET_COMPATIBILITY = 0.001
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


def label_transition_batch(ow_array, pw_array) -> np.ndarray:
    ow_offsets, ow_values = _list_offsets_and_values(ow_array)
    pw_offsets, pw_values = _list_offsets_and_values(pw_array)

    n_rows = len(ow_offsets) - 1
    if n_rows != len(pw_offsets) - 1:
        raise ValueError(
            "OW_events y PW_events deben tener el mismo numero de filas"
        )

    labels = np.zeros(n_rows, dtype=np.int8)
    if n_rows == 0:
        return labels

    ow_lengths = np.diff(ow_offsets)
    pw_lengths = np.diff(pw_offsets)
    non_empty = (ow_lengths > 0) & (pw_lengths > 0)
    if not np.any(non_empty):
        return labels

    last_ow = ow_values[ow_offsets[1:][non_empty] - 1]
    pw_starts = pw_offsets[:-1][non_empty]
    pw_has_one = np.maximum.reduceat(pw_values == 1, pw_starts)
    labels[non_empty] = ((last_ow == 0) & pw_has_one).astype(np.int8)

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


def fmt_optional(value, fmt: str = ".12g") -> str:
    if value is None:
        return "N/A"
    return format(value, fmt)


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
    event_strategy = str(params.get("event_strategy", "threshold")).strip().lower()
    if event_strategy not in {"threshold", "transitions"}:
        raise ValueError("event_strategy debe ser 'threshold' o 'transitions'")

    # --------------------------------------------------------
    # Resolver F02 para min/max de la medida
    # --------------------------------------------------------

    parent_exports = parent_outputs.get("exports", {})
    parent_f02 = parent_exports.get("parent_f02")
    measure_name = None
    value_col = None
    min_value = None
    max_value = None

    if event_strategy == "threshold":
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

    if event_strategy == "threshold" and measure_name is None:
        raise RuntimeError("F02 no exporta measure_name")
    if event_strategy == "threshold" and max_value < min_value:
        raise RuntimeError(
            f"Rango inválido en F02: min={min_value}, max={max_value}"
        )

    # --------------------------------------------------------
    # Parámetros de objetivo
    # --------------------------------------------------------

    threshold_percentage = None
    direction = None
    threshold_value = None

    if event_strategy == "threshold":
        if "OW_values" not in parent_columns or "PW_values" not in parent_columns:
            raise RuntimeError(
                "event_strategy=threshold requiere columnas OW_values y PW_values en F03"
            )
        if "threshold" not in params:
            raise ValueError("event_strategy=threshold requiere threshold")
        threshold_percentage = float(params["threshold"])
        direction = str(params["direction"]).strip().lower()

    if event_strategy == "threshold" and not 0.0 <= threshold_percentage <= 100.0:
        raise ValueError("threshold debe estar en el rango [0, 100]")
    if event_strategy == "threshold" and direction not in {"high", "low"}:
        raise ValueError("direction debe ser 'high' o 'low'")

    if event_strategy == "threshold":
        threshold_value = min_value + (threshold_percentage / 100.0) * (max_value - min_value)
        input_columns = ["OW_values", "PW_values"]
        output_column = "OW_values"
        output_list_type = parent_parquet.schema_arrow.field(output_column).type
        label_rule = f"any(PW_values {direction} threshold)"
        default_prediction_name = f"{measure_name}_{direction}_{threshold_percentage:g}pct"
    else:
        if "OW_events" not in parent_columns or "PW_events" not in parent_columns:
            raise RuntimeError(
                "event_strategy=transitions requiere columnas OW_events y PW_events en F03"
        )
        input_columns = ["OW_events", "PW_events"]
        output_column = "OW_events"
        output_list_type = parent_parquet.schema_arrow.field(output_column).type
        label_rule = "last(OW_events) == 0 AND any(PW_events == 1)"
        default_prediction_name = "event_transition_0_to_1"

    prediction_name = params.get(
        "prediction_name",
        default_prediction_name,
    )

    print("[INFO] Objetivo de predicción:")
    print(f"  event_strategy        = {event_strategy}")
    print(f"  label_rule            = {label_rule}")
    print(f"  measure_name          = {measure_name}")
    print(f"  direction             = {direction}")
    print(f"  threshold_percentage  = {threshold_percentage}")
    print(f"  threshold_value       = {threshold_value}")

    # --------------------------------------------------------
    # Etiquetado
    # --------------------------------------------------------

    output_path = variant_dir / "04_targets.parquet"
    tmp_output_path = variant_dir / "04_targets.tmp.parquet"
    if tmp_output_path.exists():
        tmp_output_path.unlink()

    schema = pa.schema([
        (output_column, output_list_type),
        ("label", pa.int8()),
    ])

    batch_size = int(params.get("batch_size", 50_000))
    if batch_size <= 0:
        raise ValueError("batch_size debe ser mayor que 0")
    compute_dedup_stats = require_bool(params.get("compute_dedup_stats", False), "compute_dedup_stats")

    total = 0
    positives = 0
    dedup = OWDedupStats() if compute_dedup_stats else None

    writer = pq.ParquetWriter(tmp_output_path, schema, compression="snappy")
    try:
        for batch in parent_parquet.iter_batches(
            batch_size=batch_size,
            columns=input_columns,
        ):
            ow_array = batch.column(batch.schema.get_field_index(input_columns[0]))
            pw_array = batch.column(batch.schema.get_field_index(input_columns[1]))
            if event_strategy == "transitions":
                labels = label_transition_batch(ow_array, pw_array)
            else:
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
    target_candidate_checks = [(measure_name, direction)] if measure_name and direction else []
    target_compatible = positive_ratio >= MIN_POSITIVE_RATIO_FOR_TARGET_COMPATIBILITY
    incompatibility_reason = None
    if not target_compatible:
        incompatibility_reason = (
            f"positive_ratio={positive_ratio:.6f} below minimum "
            f"{MIN_POSITIVE_RATIO_FOR_TARGET_COMPATIBILITY:.6f}"
        )

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
    print(f"[INFO] Target compatible: {target_compatible}")
    if incompatibility_reason is not None:
        print(f"[WARN] Target incompatible: {incompatibility_reason}")

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
        <p>Event strategy: {event_strategy}</p>
        <p>Label rule: {label_rule}</p>
        <p>Measure: {measure_name}</p>
        <p>Value column: {value_col}</p>
        <p>Direction: {direction}</p>
        <p>Threshold percentage: {fmt_optional(threshold_percentage, ".6f")}</p>
        <p>Threshold value: {fmt_optional(threshold_value)}</p>
        <p>Min value: {fmt_optional(min_value)}</p>
        <p>Max value: {fmt_optional(max_value)}</p>
        <p>Total windows: {total}</p>
        <p>Positives: {positives}</p>
        <p>Negatives: {negatives}</p>
        <p>Positive ratio: {positive_ratio:.6f}</p>
        <p>Negative ratio: {negative_ratio:.6f}</p>
        <p>Target compatible: {target_compatible}</p>
        <p>Incompatibility reason: {incompatibility_reason}</p>
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

    artifacts = {
        "report": {
            "path": report_path.name,
            "sha256": sha256_of_file(report_path),
        },
    }
    if target_compatible:
        if output_path.exists():
            output_path.unlink()
        tmp_output_path.replace(output_path)
        artifacts["dataset"] = {
            "path": output_path.name,
            "sha256": sha256_of_file(output_path),
        }
    else:
        if tmp_output_path.exists():
            tmp_output_path.unlink()
        if output_path.exists():
            output_path.unlink()

    outputs_content = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": artifacts,
        "exports": {
            "Tu": parent_exports.get("Tu", params.get("Tu")),
            "OW": parent_exports.get("OW", params.get("OW")),
            "LT": parent_exports.get("LT", params.get("LT")),
            "PW": parent_exports.get("PW", params.get("PW")),
            "prediction_name": prediction_name,
            "event_strategy": event_strategy,
            "label_rule": label_rule,
            "input_window_column": output_column,
            "measure_name": measure_name,
            "value_col": value_col,
            "direction": direction,
            "threshold_percentage": (
                float(threshold_percentage) if threshold_percentage is not None else None
            ),
            "threshold_value": float(threshold_value) if threshold_value is not None else None,
            "min_value": float(min_value) if min_value is not None else None,
            "max_value": float(max_value) if max_value is not None else None,
            "window_strategy": window_strategy,
            "parent_f03": parent_variant,
            "parent_f02": parent_f02,
            "n_windows": int(total),
            "n_windows_pos": int(positives),
            "n_windows_neg": int(negatives),
            "n_positive": int(positives),
            "n_negative": int(negatives),
            "positive_ratio": float(positive_ratio),
            "negative_ratio": float(negative_ratio),
            "class_balance_ratio": float(positive_ratio),
            "target_compatible": bool(target_compatible),
            "incompatibility_reason": incompatibility_reason,
            "target_candidate_checks": [
                {"measure": measure, "direction": direction}
                for measure, direction in target_candidate_checks
            ],
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
            "n_positive": int(positives),
            "n_negative": int(negatives),
            "target_compatible": bool(target_compatible),
            "incompatibility_reason": incompatibility_reason,
            "threshold_value": float(threshold_value) if threshold_value is not None else None,
        },
        "provenance": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
    }

    save_outputs_yaml(variant_dir, outputs_content)
    validate_outputs(PHASE, outputs_content)

    if target_compatible:
        print(f"\n===== FASE {PHASE} COMPLETADA =====")
    else:
        print(f"\n===== FASE {PHASE} COMPLETADA SIN DATASET =====")


if __name__ == "__main__":
    main()
