import re
import shutil
import struct
from pathlib import Path
from typing import Any

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


def _c_type_for_input_dtype(input_dtype: str) -> str:
    dtype = str(input_dtype or "").strip().lower()
    if dtype == "int8":
        return "int8_t"
    if dtype == "uint8":
        return "uint8_t"
    raise RuntimeError(f"Unsupported TFLite input dtype for edge input buffer: {input_dtype}")


def _range_for_input_dtype(input_dtype: str) -> tuple[int, int]:
    dtype = str(input_dtype or "").strip().lower()
    if dtype == "int8":
        return -128, 127
    if dtype == "uint8":
        return 0, 255
    raise RuntimeError(f"Unsupported TFLite input dtype for embedded input data: {input_dtype}")


TFLITE_TENSOR_TYPE_NAMES = {
    0: "float32",
    2: "int32",
    3: "uint8",
    4: "int64",
    9: "int8",
    10: "float16",
}


def _read_uoffset(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<I", buf, offset)[0]


def _read_soffset(buf: bytes, offset: int) -> int:
    return struct.unpack_from("<i", buf, offset)[0]


def _table_field_pos(buf: bytes, table_pos: int, field_id: int) -> int | None:
    vtable_pos = table_pos - _read_soffset(buf, table_pos)
    vtable_size = struct.unpack_from("<H", buf, vtable_pos)[0]
    field_entry = 4 + field_id * 2
    if field_entry + 2 > vtable_size:
        return None
    field_offset = struct.unpack_from("<H", buf, vtable_pos + field_entry)[0]
    if field_offset == 0:
        return None
    return table_pos + field_offset


def _table_ref(buf: bytes, table_pos: int, field_id: int) -> int | None:
    field_pos = _table_field_pos(buf, table_pos, field_id)
    if field_pos is None:
        return None
    return field_pos + _read_uoffset(buf, field_pos)


def _vector_pos(buf: bytes, table_pos: int, field_id: int) -> int | None:
    field_pos = _table_field_pos(buf, table_pos, field_id)
    if field_pos is None:
        return None
    return field_pos + _read_uoffset(buf, field_pos)


def _vector_len(buf: bytes, vector_pos: int) -> int:
    return struct.unpack_from("<I", buf, vector_pos)[0]


def _vector_table(buf: bytes, vector_pos: int, index: int) -> int:
    elem_pos = vector_pos + 4 + index * 4
    return elem_pos + _read_uoffset(buf, elem_pos)


def _vector_int32(buf: bytes, vector_pos: int) -> list[int]:
    n = _vector_len(buf, vector_pos)
    start = vector_pos + 4
    return [struct.unpack_from("<i", buf, start + i * 4)[0] for i in range(n)]


def _vector_float32(buf: bytes, vector_pos: int) -> list[float]:
    n = _vector_len(buf, vector_pos)
    start = vector_pos + 4
    return [struct.unpack_from("<f", buf, start + i * 4)[0] for i in range(n)]


def _vector_int64(buf: bytes, vector_pos: int) -> list[int]:
    n = _vector_len(buf, vector_pos)
    start = vector_pos + 4
    return [struct.unpack_from("<q", buf, start + i * 8)[0] for i in range(n)]


def inspect_tflite_input_quantization_flatbuffer(tflite_path: Path) -> dict[str, Any]:
    buf = tflite_path.read_bytes()
    model_pos = _read_uoffset(buf, 0)

    subgraphs_vec = _vector_pos(buf, model_pos, 2)
    if subgraphs_vec is None or _vector_len(buf, subgraphs_vec) < 1:
        raise RuntimeError(f"TFLite model has no subgraphs: {tflite_path}")
    subgraph_pos = _vector_table(buf, subgraphs_vec, 0)

    inputs_vec = _vector_pos(buf, subgraph_pos, 1)
    if inputs_vec is None or _vector_len(buf, inputs_vec) != 1:
        n_inputs = 0 if inputs_vec is None else _vector_len(buf, inputs_vec)
        raise RuntimeError(f"TFLite model must have exactly 1 input, got {n_inputs}")
    input_tensor_index = _vector_int32(buf, inputs_vec)[0]

    tensors_vec = _vector_pos(buf, subgraph_pos, 0)
    if tensors_vec is None or input_tensor_index >= _vector_len(buf, tensors_vec):
        raise RuntimeError(f"TFLite input tensor index out of range: {input_tensor_index}")
    tensor_pos = _vector_table(buf, tensors_vec, input_tensor_index)

    type_pos = _table_field_pos(buf, tensor_pos, 1)
    tensor_type = struct.unpack_from("<b", buf, type_pos)[0] if type_pos is not None else None
    dtype = TFLITE_TENSOR_TYPE_NAMES.get(tensor_type, f"tflite_type_{tensor_type}")

    shape_vec = _vector_pos(buf, tensor_pos, 0)
    shape = _vector_int32(buf, shape_vec) if shape_vec is not None else None

    quant_pos = _table_ref(buf, tensor_pos, 4)
    scale = 0.0
    zero_point = 0
    if quant_pos is not None:
        scale_vec = _vector_pos(buf, quant_pos, 2)
        zero_vec = _vector_pos(buf, quant_pos, 3)
        scales = _vector_float32(buf, scale_vec) if scale_vec is not None else []
        zeros = _vector_int64(buf, zero_vec) if zero_vec is not None else []
        if scales:
            scale = float(scales[0])
        if zeros:
            zero_point = int(zeros[0])

    if dtype in {"int8", "uint8"} and scale <= 0.0:
        raise RuntimeError(f"TFLite integer input has invalid quantization scale: {scale}")

    return {
        "input_dtype": dtype,
        "input_quant_scale": scale,
        "input_quant_zero_point": zero_point,
        "input_shape": shape,
    }


def inspect_tflite_input_quantization(tflite_path: Path) -> dict[str, Any]:
    try:
        import tensorflow as tf  # type: ignore
    except Exception:
        try:
            from tflite_runtime.interpreter import Interpreter  # type: ignore
        except Exception as exc:
            return inspect_tflite_input_quantization_flatbuffer(tflite_path)
        interpreter = Interpreter(model_path=str(tflite_path))
    else:
        interpreter = tf.lite.Interpreter(model_path=str(tflite_path))

    interpreter.allocate_tensors()
    input_details = interpreter.get_input_details()
    if len(input_details) != 1:
        raise RuntimeError(f"TFLite model must have exactly 1 input, got {len(input_details)}")

    detail = input_details[0]
    dtype = getattr(detail.get("dtype"), "__name__", None) or str(detail.get("dtype"))
    if "int8" in dtype:
        dtype = "int8"
    elif "uint8" in dtype:
        dtype = "uint8"

    scale, zero_point = detail.get("quantization", (0.0, 0))
    if dtype in {"int8", "uint8"} and (scale is None or float(scale) <= 0.0):
        raise RuntimeError(f"TFLite integer input has invalid quantization scale: {scale}")

    shape = detail.get("shape")
    return {
        "input_dtype": dtype,
        "input_quant_scale": float(scale or 0.0),
        "input_quant_zero_point": int(zero_point or 0),
        "input_shape": shape.tolist() if hasattr(shape, "tolist") else shape,
    }


def generate_runtime_config(path: Path, ow, mti_ms, tu_ms, input_dtype: str = "int8"):
    tunit_ms = int(round(tu_ms))
    ow_ms = ow * tunit_ms
    mti_ms_int = int(round(float(mti_ms)))
    event_c_type = _c_type_for_input_dtype(input_dtype)

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

typedef {event_c_type} event_t;

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
    max_rows: int | None = None,
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

    if max_rows is not None:
        max_rows = int(max_rows)
        if max_rows < 1:
            raise RuntimeError("max_rows must be >= 1 when provided")
        df = df.head(max_rows)

    for column in df.select_dtypes(include=["object"]).columns:
        df[column] = df[column].map(
            lambda value: " ".join(str(value).split())
            if "\n" in str(value) or "\r" in str(value)
            else value
        )

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



def _parse_input_sequence_cell(value, min_value: int, max_value: int) -> list[int]:
    if value is None:
        return []

    text = str(value).strip()
    if not text or text == "[]":
        return []

    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    parsed: list[int] = []
    for n in nums:
        v = int(round(float(n)))
        if v < min_value or v > max_value:
            raise RuntimeError(f"Input value {v} out of allowed range {min_value}..{max_value}.")
        parsed.append(v)

    return parsed


def _parse_raw_sequence_cell(value) -> list[float]:
    if value is None:
        return []

    text = str(value).strip()
    if not text or text == "[]":
        return []

    return [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", text)]


def _quantize_raw_sequence(
    raw_values: list[float],
    *,
    input_dtype: str,
    input_max_len: int,
    normalization_mean: float,
    normalization_std: float,
    input_quant_scale: float,
    input_quant_zero_point: int,
) -> list[int]:
    if input_max_len <= 0:
        raise RuntimeError(f"input_max_len must be > 0, got {input_max_len}")
    if normalization_std <= 0.0:
        raise RuntimeError(f"normalization_std must be > 0, got {normalization_std}")
    if input_quant_scale <= 0.0:
        raise RuntimeError(f"input_quant_scale must be > 0, got {input_quant_scale}")

    min_value, max_value = _range_for_input_dtype(input_dtype)
    padded = [0.0] * input_max_len
    trunc = [float(v) for v in raw_values[-input_max_len:]]
    if trunc:
        padded[-len(trunc):] = trunc

    quantized = []
    for raw in padded:
        normalized = (raw - normalization_mean) / normalization_std
        q = int(round(normalized / input_quant_scale + input_quant_zero_point))
        q = max(min_value, min(max_value, q))
        quantized.append(q)

    return quantized


def parse_raw_input_sequence_cell(value) -> list[float]:
    return _parse_raw_sequence_cell(value)


def quantize_raw_input_sequence(
    raw_values: list[float],
    *,
    input_dtype: str,
    input_max_len: int,
    normalization_mean: float,
    normalization_std: float,
    input_quant_scale: float,
    input_quant_zero_point: int,
) -> list[int]:
    return _quantize_raw_sequence(
        raw_values,
        input_dtype=input_dtype,
        input_max_len=input_max_len,
        normalization_mean=normalization_mean,
        normalization_std=normalization_std,
        input_quant_scale=input_quant_scale,
        input_quant_zero_point=input_quant_zero_point,
    )


def generate_memory_events_header(
    csv_path: Path,
    out_path: Path,
    input_dtype: str = "int8",
    max_rows: int | None = None,
    input_max_len: int | None = None,
    normalization_mean: float | None = None,
    normalization_std: float | None = None,
    input_quant_scale: float | None = None,
    input_quant_zero_point: int | None = None,
):
    min_value, max_value = _range_for_input_dtype(input_dtype)
    df = pd.read_csv(csv_path, sep=";")
    input_rows: list[list[int]] = []

    rows_df = df if max_rows is None else df.head(max_rows)

    if "OW_events" in rows_df.columns:
        for raw in rows_df["OW_events"].tolist():
            input_rows.append(_parse_input_sequence_cell(raw, min_value, max_value))
    elif "OW_values" in rows_df.columns:
        missing = [
            name
            for name, value in {
                "input_max_len": input_max_len,
                "normalization_mean": normalization_mean,
                "normalization_std": normalization_std,
                "input_quant_scale": input_quant_scale,
                "input_quant_zero_point": input_quant_zero_point,
            }.items()
            if value is None
        ]
        if missing:
            raise RuntimeError(
                "OW_values input requires F06 preprocessing metadata: "
                + ", ".join(missing)
            )
        for raw in rows_df["OW_values"].tolist():
            raw_values = _parse_raw_sequence_cell(raw)
            input_rows.append(
                _quantize_raw_sequence(
                    raw_values,
                    input_dtype=input_dtype,
                    input_max_len=int(input_max_len),
                    normalization_mean=float(normalization_mean),
                    normalization_std=float(normalization_std),
                    input_quant_scale=float(input_quant_scale),
                    input_quant_zero_point=int(input_quant_zero_point),
                )
            )
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
                    if event_id < min_value or event_id > max_value:
                        raise RuntimeError(
                            f"Input value {event_id} out of allowed range {min_value}..{max_value}."
                        )
                    values.append(event_id)
                input_rows.append(values)

    if not input_rows:
        input_rows = [[0]]

    lines = [
        "#ifndef MEMORY_EVENTS_H",
        "#define MEMORY_EVENTS_H",
        "",
        '#include "config.h"',
        "",
    ]

    for idx, row in enumerate(input_rows):
        encoded = row if row else [0]
        row_values = ", ".join(str(v) for v in encoded)
        lines.append(f"static const event_t memory_event_{idx}[] = {{ {row_values} }};")

    lines.append("")
    lines.append("static const event_t *memory_events[] = {")
    for idx in range(len(input_rows)):
        lines.append(f"    memory_event_{idx},")
    lines.append("};")
    lines.append("")
    lines.append("static const size_t memory_events_lengths[] = {")
    for row in input_rows:
        lines.append(f"    {len(row)},")
    lines.append("};")
    lines.append("")
    lines.append(f"static const size_t memory_events_count = {len(input_rows)};")
    lines.append("")
    lines.append("#endif")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines) + "\n")
