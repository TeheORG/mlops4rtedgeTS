import re
import shutil
from pathlib import Path

import pandas as pd
from scripts.core.phase_io import load_phase_outputs, load_variant_params, load_yaml_file


def ensure_clean_dir(path: Path):
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def resolve_platform(params: dict, phase_tag: str) -> str:
    platform = params.get("platform")
    if not platform:
        raise RuntimeError(
            f"[{phase_tag}] parameter 'platform' es obligatorio en params.yaml "
            "(ejemplo: platform: esp32)"
        )
    return str(platform).strip().lower()


def resolve_template_project_dir(edge_dir: Path, platform: str, phase_tag: str) -> Path:
    template_dir = edge_dir / platform / "template_project"
    if not template_dir.exists():
        raise RuntimeError(
            f"[{phase_tag}] Plantilla edge no encontrada para platform={platform}: {template_dir}"
        )
    return template_dir


def resolve_runner_dir(edge_dir: Path, platform: str) -> Path | None:
    runner_dir = edge_dir / platform / "runner"
    if runner_dir.exists():
        return runner_dir
    return None


def compute_tu_ms(tu_dataset, time_scale):
    tu_edge = tu_dataset * time_scale
    return tu_edge * 1000.0


def compute_recommended_drain_seconds(ow, lt, tu_ms, mti_ms):
    tunit_s = float(tu_ms) / 1000.0
    ow_lt_s = float((ow or 0) + (lt or 0)) * tunit_s
    ow_mti_s = float(ow or 0) * tunit_s + float(mti_ms) / 1000.0
    return max(5.0, ow_lt_s, ow_mti_s)


def sanitize_name(name: str):
    return "".join(c if c.isalnum() else "_" for c in name)


def tflites_to_models_data_c(models: list[dict], out_path: Path, phase_tag: str):
    if not models:
        raise RuntimeError(f"No models configured for {phase_tag}")

    models_sorted = sorted(models, key=lambda m: int(m.get("id", 0)))

    blocks = [
        '#include "models_data.h"',
        "",
    ]

    model_rows = []

    for model in models_sorted:
        tflite_path = Path(model["tflite_path"])
        model_name = str(model["name"])
        threshold = float(model["threshold"])
        itmax = int(model["itmax"])
        arena_required = int(model["arena_required"])

        data = tflite_path.read_bytes()
        bytes_per_line = 12
        lines = []
        for i in range(0, len(data), bytes_per_line):
            chunk = data[i:i + bytes_per_line]
            lines.append(", ".join(f"0x{b:02x}" for b in chunk))

        array_body = ",\n    ".join(lines)
        safe = sanitize_name(model_name)

        blocks.append(f"static const unsigned char MG_{safe}[] = {{")
        blocks.append(f"    {array_body}")
        blocks.append("};")
        blocks.append("")
        blocks.append(f"static const size_t MG_{safe}_len = {len(data)};")
        blocks.append(f"static const uint64_t MG_{safe}_exec_time = {itmax};")
        blocks.append(f"static const float MG_{safe}_threshold = {threshold}f;")
        blocks.append(f"static const size_t MG_{safe}_arena_required = {arena_required};")
        blocks.append("")
        blocks.append(f"static const event_t MG_{safe}_triggers[] = {{0}};")
        blocks.append(f"static const size_t MG_{safe}_trigger_count = 0;")
        blocks.append(f"static const bool MG_{safe}_trigger_all = true;")
        blocks.append("")

        model_rows.append("{")
        model_rows.append(f'    .name = "{model_name}",')
        model_rows.append(f"    .data = MG_{safe},")
        model_rows.append(f"    .size = MG_{safe}_len,")
        model_rows.append(f"    .exec_time = MG_{safe}_exec_time,")
        model_rows.append(f"    .threshold = MG_{safe}_threshold,")
        model_rows.append(f"    .arena_required = MG_{safe}_arena_required,")
        model_rows.append(f"    .triggers = MG_{safe}_triggers,")
        model_rows.append(f"    .trigger_count = MG_{safe}_trigger_count,")
        model_rows.append(f"    .trigger_all = MG_{safe}_trigger_all")
        model_rows.append("},")

    blocks.append("const model_t g_models[] = {")
    blocks.extend(model_rows)
    blocks.append("};")
    blocks.append("")
    blocks.append("const size_t g_models_count = sizeof(g_models)/sizeof(g_models[0]);")
    blocks.append("")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(blocks))


TFLM_RESOLVER_MAP = {
    "ADD": "AddAdd",
    "SUB": "AddSub",
    "MUL": "AddMul",
    "DIV": "AddDiv",
    "FULLY_CONNECTED": "AddFullyConnected",
    "CONV_2D": "AddConv2D",
    "DEPTHWISE_CONV_2D": "AddDepthwiseConv2D",
    "AVERAGE_POOL_2D": "AddAveragePool2D",
    "MAX_POOL_2D": "AddMaxPool2D",
    "RESHAPE": "AddReshape",
    "SOFTMAX": "AddSoftmax",
    "LOGISTIC": "AddLogistic",
    "RELU": "AddRelu",
    "RELU6": "AddRelu6",
    "TANH": "AddTanh",
    "PAD": "AddPad",
    "MEAN": "AddMean",
    "QUANTIZE": "AddQuantize",
    "DEQUANTIZE": "AddDequantize",
    "CAST": "AddCast",
    "EXPAND_DIMS": "AddExpandDims",
    "GATHER": "AddGather",
    "REDUCE_MAX": "AddReduceMax",
}


def generate_tflm_resolver(operators, out_path: Path, phase_tag: str):
    base_ops = {"RESHAPE", "QUANTIZE", "DEQUANTIZE"}
    ops = sorted(set(operators) | base_ops)

    methods = []
    for op in ops:
        if op not in TFLM_RESOLVER_MAP:
            raise RuntimeError(f"[{phase_tag}] operador no soportado: {op}")
        methods.append(TFLM_RESOLVER_MAP[op])

    resolver_size = len(methods)

    lines = [
        f"// Auto-generated by {phase_tag}",
        "#ifndef MODEL_RESOLVER_H",
        "#define MODEL_RESOLVER_H",
        "",
        f"#define MODEL_OPERATOR_COUNT {resolver_size}",
        "",
        '#include "tensorflow/lite/micro/micro_mutable_op_resolver.h"',
        "",
        "inline void SetupModelResolver("
        "tflite::MicroMutableOpResolver<MODEL_OPERATOR_COUNT>& resolver) {",
    ]

    for method in methods:
        lines.append(f"  resolver.{method}();")

    lines.append("}")
    lines.append("")
    lines.append("#endif")

    out_path.write_text("\n".join(lines))


def generate_runtime_config(path: Path, ow, mti_ms, tu_ms):
    tunit_ms = int(round(tu_ms))
    ow_ms = ow * tunit_ms
    mti_ms_int = int(round(float(mti_ms)))

    code = f"""
#ifndef CONFIG_H
#define CONFIG_H

#include <stdint.h>

#define ENABLE_TRACES 1
#define USE_SERIAL_READER 0

#define TUNIT_MS {tunit_ms}
#define OW_MS {ow_ms}
#define MTI_MS {mti_ms_int}
#define MIT_MS MTI_MS

typedef uint8_t event_t;

#endif
"""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(code)


def copy_dataset_to_csv(
    src_path: Path,
    csv_variant: Path,
    csv_project: Path,
    *,
    allow_csv: bool,
):
    suffix = src_path.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(src_path)
    elif suffix == ".csv" and allow_csv:
        df = pd.read_csv(src_path)
    else:
        if allow_csv:
            raise RuntimeError(f"Dataset source no soportado: {src_path} (se espera .parquet o .csv)")
        raise RuntimeError(f"Dataset source no soportado: {src_path} (se espera .parquet)")

    csv_variant.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_variant, index=False, sep=";")

    csv_project.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(csv_variant, csv_project)


def copy_or_convert_dataset_to_csv(
    src_path: Path,
    csv_output: Path,
    *,
    allow_csv: bool,
):
    suffix = src_path.suffix.lower()
    csv_output.parent.mkdir(parents=True, exist_ok=True)

    if suffix == ".parquet":
        df = pd.read_parquet(src_path)
        df.to_csv(csv_output, index=False, sep=";")
    elif suffix == ".csv" and allow_csv:
        shutil.copy2(src_path, csv_output)
    else:
        if allow_csv:
            raise RuntimeError(f"Dataset source no soportado: {src_path} (se espera .parquet o .csv)")
        raise RuntimeError(f"Dataset source no soportado: {src_path} (se espera .parquet)")


def _parse_events_cell(value, max_event_id: int) -> list[int]:
    if value is None:
        return []

    text = str(value).strip()
    if not text or text == "[]":
        return []

    nums = re.findall(r"-?\d+", text)
    parsed: list[int] = []
    for n in nums:
        v = int(n)
        if v < 0:
            raise RuntimeError(f"Negative event id not supported: {v}")
        if v > max_event_id:
            raise RuntimeError(
                f"Event id {v} out of allowed range 0 or 1..{max_event_id}. "
                "Regenera ancestros o revisa el catálogo F02/F03."
            )
        parsed.append(v)

    return parsed


def generate_memory_events_header(
    csv_path: Path,
    out_path: Path,
    event_type_count: int,
    max_rows: int | None = None,
):
    if event_type_count < 1:
        raise RuntimeError("event_type_count must be >= 1")
    if event_type_count > 256:
        raise RuntimeError(
            f"event_type_count={event_type_count} exceeds uint8 capacity (256)."
        )

    max_event_id = event_type_count
    df = pd.read_csv(csv_path, sep=";")
    events: list[list[int]] = []

    rows_df = df if max_rows is None else df.head(max_rows)

    if "OW_events" in rows_df.columns:
        for raw in rows_df["OW_events"].tolist():
            events.append(_parse_events_cell(raw, max_event_id))
    else:
        numeric_df = rows_df.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
        drop_cols = {"label", "target", "y", "pred", "prediction", "class"}
        keep_cols = [c for c in numeric_df.columns if str(c).strip().lower() not in drop_cols]

        if keep_cols:
            numeric_df = numeric_df[keep_cols]

        if not numeric_df.empty:
            numeric_df = numeric_df.fillna(0)
            for row in numeric_df.to_numpy().tolist():
                values = []
                for v in row:
                    event_id = int(round(float(v)))
                    if event_id < 0:
                        raise RuntimeError(f"Negative event id not supported: {event_id}")
                    if event_id > max_event_id:
                        raise RuntimeError(
                            f"Event id {event_id} out of allowed range 0 or 1..{max_event_id}. "
                            "Regenera ancestros o revisa el catálogo F02/F03."
                        )
                    values.append(event_id)
                events.append(values)

    if not events:
        events = [[0]]

    lines = [
        "#ifndef MEMORY_EVENTS_H",
        "#define MEMORY_EVENTS_H",
        "",
        '#include "config.h"',
        "",
    ]

    for idx, row in enumerate(events):
        encoded = row if row else [0]
        row_values = ", ".join(str(v) for v in encoded)
        lines.append(f"static const event_t memory_event_{idx}[] = {{ {row_values} }};")

    lines.append("")
    lines.append("static const event_t *memory_events[] = {")
    for idx in range(len(events)):
        lines.append(f"    memory_event_{idx},")
    lines.append("};")
    lines.append("")
    lines.append("static const size_t memory_events_lengths[] = {")
    for row in events:
        lines.append(f"    {len(row)},")
    lines.append("};")
    lines.append("")
    lines.append(f"static const size_t memory_events_count = {len(events)};")
    lines.append("")
    lines.append("#endif")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")