#!/usr/bin/env python3
"""
F06 — QUANTIZATION & EDGE ADAPTATION

Nueva lógica:
  1. Copiar dataset y modelo float (fase autocontenida).
  2. Analizar operadores del modelo float exportado.
  3. Verificar compatibilidad con deployment target.
  4. Si NO compatible:
        - edge_capable = False
        - generar report + outputs.yaml
        - NO cuantizar
  5. Si compatible:
        - cuantizar
        - recalibrar threshold
        - extraer operadores finales
        - estimar memoria
        - edge_capable = True

IMPORTANTE (refactor):
  - F06 ya NO genera operators_resolver.cc.
  - F06 exporta la lista de operadores en outputs.yaml (exports.operators).
  - La generación de operators_resolver.cc se delega a F07/F08.
"""

import argparse
import time
import shutil
import platform
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

import numpy as np
import pandas as pd
import tensorflow as tf
import yaml
from sklearn.metrics import (
    precision_score,
    recall_score,
    f1_score,
    average_precision_score,
    confusion_matrix,
    precision_recall_curve,
)

from scripts.core.artifacts import (
    PROJECT_ROOT,
    get_variant_dir,
    save_outputs_yaml,
    sha256_of_file,
)
from scripts.core.phase_io import load_phase_outputs, load_variant_params
from scripts.core.traceability import validate_outputs

from tensorflow.lite.python import schema_py_generated as schema_fb

PHASE = "f06_quant"
PARENT_PHASE = "f05_modeling"
INPUT_SEQUENCE_COLUMN = "OW_values"


# ============================================================
# TFLM SUPPORT (según esp-tflite-micro 1.3.3)
# ============================================================

TFLM_SUPPORTED_OPERATORS = {
    "ADD", "SUB", "MUL", "DIV",
    "FULLY_CONNECTED",
    "CONV_2D", "DEPTHWISE_CONV_2D",
    "AVERAGE_POOL_2D", "MAX_POOL_2D",
    "RESHAPE", "SOFTMAX",
    "LOGISTIC", "RELU", "RELU6", "TANH",
    "PAD", "MEAN",
    "QUANTIZE", "DEQUANTIZE",
    "CAST", "EXPAND_DIMS", "GATHER", "REDUCE_MAX",
}


def extract_tflite_operators(model_bytes: bytes):
    """Extrae lista de operadores (únicos) y conteo desde un flatbuffer TFLite."""
    model_obj = schema_fb.Model.GetRootAsModel(model_bytes, 0)
    operator_codes = [
        model_obj.OperatorCodes(i)
        for i in range(model_obj.OperatorCodesLength())
    ]

    builtin_map = {
        v: k
        for k, v in schema_fb.BuiltinOperator.__dict__.items()
        if isinstance(v, int)
    }

    ops = []
    for s in range(model_obj.SubgraphsLength()):
        subgraph = model_obj.Subgraphs(s)
        for i in range(subgraph.OperatorsLength()):
            op = subgraph.Operators(i)
            opcode = operator_codes[op.OpcodeIndex()]
            name = builtin_map.get(opcode.BuiltinCode(), "UNKNOWN")
            ops.append(name)

    unique_ops = sorted(set(ops))
    counts = dict(Counter(ops))
    return unique_ops, counts


def check_compatibility(operators):
    """Devuelve lista de operadores NO soportados por TFLM."""
    return [op for op in operators if op not in TFLM_SUPPORTED_OPERATORS]


def compute_threshold(y_true, y_prob):
    """Calcula umbral óptimo (por F1) sobre probabilidades."""
    precisions, recalls, thresholds = precision_recall_curve(y_true, y_prob)
    f1 = 2 * (precisions * recalls) / (precisions + recalls + 1e-8)
    idx = int(np.argmax(f1))
    return float(thresholds[idx]) if idx < len(thresholds) else 0.5


def build_calibration_input(
    df: pd.DataFrame,
    label_col: str,
    model_family: str,
    model,
):
    """Construye X_calib desde OW_values como secuencia numerica continua."""
    if INPUT_SEQUENCE_COLUMN not in df.columns:
        raise RuntimeError(f"El dataset de F05 debe contener la columna '{INPUT_SEQUENCE_COLUMN}'")

    input_shape = tuple(model.input_shape)
    if model_family == "cnn1d":
        max_len = int(input_shape[1])
    elif model_family == "dense_bow":
        max_len = int(input_shape[-1])
    else:
        raise ValueError(
            f"model_family no soportada para secuencias numericas: {model_family}. "
            "Use cnn1d o dense_bow."
        )

    sequences = df[INPUT_SEQUENCE_COLUMN].tolist()
    X_2d = np.zeros((len(sequences), max_len), dtype=np.float32)
    for i, seq in enumerate(sequences):
        arr = np.asarray(seq, dtype=np.float32)
        if arr.size == 0:
            continue
        trunc = arr[-max_len:]
        X_2d[i, -len(trunc):] = trunc

    mean = float(np.mean(X_2d)) if X_2d.size else 0.0
    std = float(np.std(X_2d)) if X_2d.size else 1.0
    if std <= 0.0:
        std = 1.0
    X_2d = ((X_2d - mean) / std).astype(np.float32)

    if model_family == "cnn1d":
        X = X_2d[..., np.newaxis]
    else:
        X = X_2d

    return X, {
        "input_sequence_column": INPUT_SEQUENCE_COLUMN,
        "input_max_len": int(max_len),
        "normalization_mean": mean,
        "normalization_std": std,
    }



def sanitize_probabilities(y_prob, context=""):
    arr = np.asarray(y_prob, dtype=np.float64)
    non_finite = ~np.isfinite(arr)
    if non_finite.any():
        arr[non_finite] = 0.0
    return np.clip(arr, 0.0, 1.0)


def compute_binary_metrics(y_true, y_prob, threshold: float):
    y_prob = sanitize_probabilities(y_prob, "tflite_eval")
    y_pred = (y_prob >= threshold).astype("int32")
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    tn, fp, fn, tp = [int(v) for v in cm.ravel()]
    return {
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "pr_auc": float(average_precision_score(y_true, y_prob)),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def quantize_input_for_tflite(sample, input_detail):
    dtype = input_detail["dtype"]
    scale, zero_point = input_detail.get("quantization", (0.0, 0))
    sample = sample.astype(np.float32)
    if np.issubdtype(dtype, np.integer):
        if scale in (None, 0.0):
            raise RuntimeError("TFLite integer input has invalid quantization scale")
        q = np.round(sample / float(scale) + int(zero_point))
        info = np.iinfo(dtype)
        return np.clip(q, info.min, info.max).astype(dtype)
    return sample.astype(dtype)


def dequantize_output_from_tflite(output, output_detail):
    dtype = output_detail["dtype"]
    if np.issubdtype(dtype, np.integer):
        scale, zero_point = output_detail.get("quantization", (0.0, 0))
        if scale in (None, 0.0):
            return output.astype(np.float32)
        return (output.astype(np.float32) - int(zero_point)) * float(scale)
    return output.astype(np.float32)


def predict_tflite_probabilities(tflite_bytes: bytes, X_eval: np.ndarray):
    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()
    input_detail = interpreter.get_input_details()[0]
    output_detail = interpreter.get_output_details()[0]
    input_index = input_detail["index"]
    output_index = output_detail["index"]
    y_prob = np.zeros(len(X_eval), dtype=np.float32)
    for i in range(len(X_eval)):
        sample = X_eval[i:i + 1]
        interpreter.set_tensor(input_index, quantize_input_for_tflite(sample, input_detail))
        interpreter.invoke()
        output = dequantize_output_from_tflite(interpreter.get_tensor(output_index), output_detail).ravel()
        y_prob[i] = float(output[-1]) if output.size else 0.0
    return sanitize_probabilities(y_prob, "tflite_eval")


def slice_f05_test_set(X, y, parent_outputs: dict):
    metrics = parent_outputs.get("metrics") or {}
    n_train = int(metrics.get("n_train", 0))
    n_val = int(metrics.get("n_val", 0))
    n_test = int(metrics.get("n_test", 0))
    if n_train <= 0 or n_val < 0 or n_test <= 0:
        raise RuntimeError("Parent F05 metrics must include n_train, n_val and n_test")
    start = n_train + n_val
    end = start + n_test
    if end > len(y):
        raise RuntimeError(f"F05 test slice [{start}:{end}] exceeds dataset length {len(y)}")
    return X[start:end], y[start:end].astype("int32")

def build_tflite(model, X_calib, inference_input_dtype=tf.int8):
    """Genera modelo TFLite cuantizado a partir de un modelo Keras y X_calib."""
    converter = tf.lite.TFLiteConverter.from_keras_model(model)
    converter.optimizations = [tf.lite.Optimize.DEFAULT]

    def rep_dataset():
        for i in range(min(256, len(X_calib))):
            yield [X_calib[i:i+1].astype(np.float32)]

    converter.representative_dataset = rep_dataset
    converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
    converter.inference_input_type = inference_input_dtype
    converter.inference_output_type = tf.int8

    return converter.convert()

def inspect_quantized_tflite(tflite_bytes: bytes):
    """
    Inspecciona la firma real del modelo TFLite cuantizado.
    Verifica número de entradas/salidas, dtype y shapes.
    """
    interpreter = tf.lite.Interpreter(model_content=tflite_bytes)
    interpreter.allocate_tensors()

    input_details = interpreter.get_input_details()
    output_details = interpreter.get_output_details()

    def _dtype_name(d):
        if not d:
            return None
        dt = d[0].get("dtype")
        return np.dtype(dt).name if dt is not None else None

    def _shape_list(d):
        if not d:
            return None
        shape = d[0].get("shape")
        return shape.tolist() if shape is not None else None

    def _bytes_from_shape(d):
        if not d:
            return None
        shape = d[0].get("shape")
        if shape is None:
            return None
        # tamaño lógico mínimo; suficiente para comparar contrato de entrada/salida
        return int(np.prod(shape))

    return {
        "num_inputs": len(input_details),
        "num_outputs": len(output_details),
        "input_dtype": _dtype_name(input_details),
        "output_dtype": _dtype_name(output_details),
        "input_shape": _shape_list(input_details),
        "output_shape": _shape_list(output_details),
        "input_bytes": _bytes_from_shape(input_details),
        "output_bytes": _bytes_from_shape(output_details),
    }

# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant
    t0 = time.perf_counter()

    # ----------------------------------------------------------
    # 0. Cargar params F06 y outputs F05
    # ----------------------------------------------------------
    params_data = load_variant_params(get_variant_dir, PHASE, variant, "F06")
    params = params_data["parameters"]
    parent_variant = params_data["parent"]

    parent_outputs, parent_dir = load_phase_outputs(PROJECT_ROOT, PARENT_PHASE, parent_variant, "F06")

    parent_artifacts = parent_outputs.get("artifacts", {}) or {}
    exports_parent = parent_outputs.get("exports", {}) or {}

    dataset_path = parent_dir / parent_artifacts["labeled_dataset"]["path"]
    model_rel = (parent_artifacts.get("model") or {}).get("path")
    model_path = parent_dir / model_rel if model_rel else None
    parent_trainable = bool(exports_parent.get("trainable", model_path is not None))

    variant_dir = get_variant_dir(PHASE, variant)
    variant_dir.mkdir(parents=True, exist_ok=True)

    # Copia dataset + modelo (fase autocontenida)
    dst_dataset = variant_dir / "06_calibration_dataset.parquet"
    dst_test_dataset = variant_dir / "06_test_dataset.parquet"
    dst_model = variant_dir / "06_model_float.h5"
    shutil.copy2(dataset_path, dst_dataset)
    if parent_trainable and model_path is not None and model_path.exists():
        shutil.copy2(model_path, dst_model)

    df = pd.read_parquet(dst_dataset)
    parent_metrics = parent_outputs.get("metrics") or {}
    test_start = int(parent_metrics.get("n_train", 0)) + int(parent_metrics.get("n_val", 0))
    test_end = test_start + int(parent_metrics.get("n_test", 0))
    if 0 <= test_start < test_end <= len(df):
        df.iloc[test_start:test_end].to_parquet(dst_test_dataset)

    candidates = [
        exports_parent.get("target_column"),
        "label",
        exports_parent.get("prediction_name"),
    ]
    label_col = next((col for col in candidates if col and col in df.columns), None)

    if not label_col:
        raise RuntimeError(
            "No se pudo resolver columna objetivo. "
            "Se intentó con exports.target_column, 'label' y exports.prediction_name"
        )

    model_family = str(
        exports_parent.get("model_family")
        or params.get("model_family")
        or ""
    )

    model = None
    X = None
    y = None
    calibration_info = {}

    operators_float = []
    unsupported_float = []
    operators_quant = []
    unsupported_quant = []
    counts_float = {}
    quant_signature = None
    tflite_bytes = None
    exported_operators = None
    model_size_bytes = None
    arena_estimated_bytes = None
    footprint_estimated_bytes = None
    decision_threshold = None
    tflite_eval_threshold = float(exports_parent.get("decision_threshold", 0.5))
    tflite_test_metrics = None

    edge_capable = True
    incompat_reason = None

    if not parent_trainable:
        edge_capable = False
        incompat_reason = (
            "Parent F05 no produjo un modelo entrenable: "
            f"{exports_parent.get('incompatibility_reason') or 'motivo no especificado'}"
        )
    elif model_path is None or not model_path.exists():
        edge_capable = False
        incompat_reason = "Parent F05 no contiene artifacts.model válido"
    else:
        model = tf.keras.models.load_model(dst_model)

        X, calibration_info = build_calibration_input(
            df,
            label_col,
            model_family,
            model,
        )
        y = df[label_col].values

    # ----------------------------------------------------------
    # 1. ANALIZAR MODELO FLOAT
    # ----------------------------------------------------------
    if model is not None:
        float_tflite = tf.lite.TFLiteConverter.from_keras_model(model).convert()
        operators_float, counts_float = extract_tflite_operators(float_tflite)

        unsupported_float = check_compatibility(operators_float)

        edge_capable = len(unsupported_float) == 0
        incompat_reason = ", ".join(unsupported_float) if unsupported_float else None

        requested_input_dtype = tf.int8

        # ----------------------------------------------------------
        # 2. CUANTIZAR (solo si de momento es edge_capable)
        # ----------------------------------------------------------
        if edge_capable:
            try:
                tflite_bytes = build_tflite(
                    model,
                    X,
                    inference_input_dtype=requested_input_dtype,
                )
            except Exception as exc:
                edge_capable = False
                incompat_reason = f"Quantization failed: {exc}"
                tflite_bytes = None

        if edge_capable and tflite_bytes is not None:
            tflite_path = variant_dir / "06_model_tflite.tflite"
            tflite_path.write_bytes(tflite_bytes)

            # Inspección de firma real del modelo cuantizado
            quant_signature = inspect_quantized_tflite(tflite_bytes)

            if quant_signature["num_inputs"] != 1:
                edge_capable = False
                incompat_reason = (
                    f"Quantized model must have exactly 1 input, got "
                    f"{quant_signature['num_inputs']}"
                )

            elif quant_signature["num_outputs"] != 1:
                edge_capable = False
                incompat_reason = (
                    f"Quantized model must have exactly 1 output, got "
                    f"{quant_signature['num_outputs']}"
                )

            elif quant_signature["input_dtype"] not in {"int8", "uint8"}:
                edge_capable = False
                incompat_reason = (
                    f"Quantized model input dtype must be int8 or uint8, got "
                    f"{quant_signature['input_dtype']}"
                )

            elif quant_signature["output_dtype"] != "int8":
                edge_capable = False
                incompat_reason = (
                    f"Quantized model output dtype must be int8, got "
                    f"{quant_signature['output_dtype']}"
                )

            operators_quant, counts_quant = extract_tflite_operators(tflite_bytes)
            unsupported_quant = check_compatibility(operators_quant)

            if unsupported_quant:
                edge_capable = False
                incompat_reason = (
                    "Quantized operators not supported: " + ", ".join(unsupported_quant)
                )
            else:
                # --------------------------------------------------
                # 3. CALCULAR THRESHOLD SOBRE MODELO FLOAT
                #    (se asume que la distorsión por cuantización es pequeña)
                # --------------------------------------------------
                y_prob = model.predict(X).ravel()
                decision_threshold = compute_threshold(y, y_prob)

                model_size_bytes = len(tflite_bytes)
                arena_estimated_bytes = int(model_size_bytes * 1.5)
                footprint_estimated_bytes = model_size_bytes + arena_estimated_bytes

                # Aquí fijamos los operadores “exportables” (modelo cuantizado)
                exported_operators = operators_quant

                X_test, y_test = slice_f05_test_set(X, y, parent_outputs)
                y_tflite_prob = predict_tflite_probabilities(tflite_bytes, X_test)
                tflite_test_metrics = compute_binary_metrics(
                    y_test,
                    y_tflite_prob,
                    tflite_eval_threshold,
                )

                # --------------------------------------------------
                # 4. MANIFEST EEDU LIGERO (sin resolver de operadores)
                # --------------------------------------------------
                eedu_dir = variant_dir / "eedu"
                eedu_dir.mkdir(exist_ok=True)

                manifest = {
                    "phase": PHASE,
                    "variant": variant,
                    "parent_phase": PARENT_PHASE,
                    "parent_variant": parent_variant,
                    "model_family": model_family,
                    "operators": operators_quant,
                    "model_size_bytes": model_size_bytes,
                    "calibration": calibration_info,
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "runtime": {
                        "tflite_version": tf.__version__,
                        "python_platform": platform.platform(),
                    },
                }

                (eedu_dir / "eedu_manifest.yaml").write_text(
                    yaml.safe_dump(manifest, sort_keys=False)
                )

    execution_time = time.perf_counter() - t0

    # ----------------------------------------------------------
    # 5. REPORT HTML
    # ----------------------------------------------------------
    report_path = variant_dir / "06_quant_report.html"
    report_html = f"""
    <html>
    <body>
      <h1>F06 Quantization — {variant}</h1>
      <p><b>Parent F05:</b> {parent_variant}</p>
      <p><b>Model family:</b> {model_family}</p>
      <h2>Compatibility</h2>
      <ul>
        <li>edge_capable = {edge_capable}</li>
        <li>incompatibility_reason = {incompat_reason}</li>
        <li>operators_float_detected = {len(operators_float)}</li>
        <li>unsupported_float = {len(unsupported_float)}</li>
        <li>operators_quant_detected = {len(operators_quant)}</li>
        <li>unsupported_quant = {len(unsupported_quant)}</li>
      </ul>
      <h2>Quantization</h2>
      <ul>
        <li>decision_threshold = {decision_threshold}</li>
        <li>model_size_bytes = {model_size_bytes}</li>
        <li>arena_estimated_bytes = {arena_estimated_bytes}</li>
        <li>footprint_estimated_bytes = {footprint_estimated_bytes}</li>
      </ul>
      <h2>TFLite Test Evaluation</h2>
      <ul>
        <li>threshold = {tflite_eval_threshold}</li>
        <li>precision = {None if tflite_test_metrics is None else tflite_test_metrics["precision"]}</li>
        <li>recall = {None if tflite_test_metrics is None else tflite_test_metrics["recall"]}</li>
        <li>f1 = {None if tflite_test_metrics is None else tflite_test_metrics["f1"]}</li>
        <li>pr_auc = {None if tflite_test_metrics is None else tflite_test_metrics["pr_auc"]}</li>
        <li>false_positives = {None if tflite_test_metrics is None else tflite_test_metrics["fp"]}</li>
        <li>false_negatives = {None if tflite_test_metrics is None else tflite_test_metrics["fn"]}</li>
      </ul>
      <h2>Execution</h2>
      <p>execution_time = {execution_time:.2f} s</p>
    </body>
    </html>
    """
    report_path.write_text(report_html, encoding="utf-8")

    # ----------------------------------------------------------
    # 6. ARTIFACTS
    # ----------------------------------------------------------
    artifacts = {
        "calibration_dataset": {
            "path": dst_dataset.name,
            "sha256": sha256_of_file(dst_dataset),
        },
        "report": {
            "path": report_path.name,
            "sha256": sha256_of_file(report_path),
        },
    }


    if dst_test_dataset.exists():
        artifacts["test_dataset"] = {
            "path": dst_test_dataset.name,
            "sha256": sha256_of_file(dst_test_dataset),
        }

    if dst_model.exists():
        artifacts["model_float"] = {
            "path": dst_model.name,
            "sha256": sha256_of_file(dst_model),
        }

    tflite_path = variant_dir / "06_model_tflite.tflite"
    if tflite_path.exists():
        artifacts["model_tflite"] = {
            "path": tflite_path.name,
            "sha256": sha256_of_file(tflite_path),
        }

    eedu_manifest_path = variant_dir / "eedu" / "eedu_manifest.yaml"
    if eedu_manifest_path.exists():
        artifacts["eedu_manifest"] = {
            "path": str(eedu_manifest_path.relative_to(variant_dir)),
            "sha256": sha256_of_file(eedu_manifest_path),
        }

    # ----------------------------------------------------------
    # 7. EXPORTS
    # ----------------------------------------------------------
    resolved_tu = params.get("Tu") if params.get("Tu") is not None else exports_parent.get("Tu")
    resolved_ow = params.get("OW") if params.get("OW") is not None else exports_parent.get("OW")
    resolved_lt = params.get("LT") if params.get("LT") is not None else exports_parent.get("LT")
    resolved_pw = params.get("PW") if params.get("PW") is not None else exports_parent.get("PW")
    resolved_prediction_name = params.get("prediction_name") or exports_parent.get("prediction_name")
    if not resolved_prediction_name:
        raise RuntimeError("No se pudo resolver prediction_name para F06")

    if not model_family:
        raise RuntimeError("No se pudo resolver model_family para F06")

    runtime_model_name = f"{resolved_prediction_name}-{model_family}-{parent_variant}"

    exports_out = {
        "Tu": int(resolved_tu),
        "OW": int(resolved_ow),
        "LT": int(resolved_lt),
        "PW": int(resolved_pw),
        "prediction_name": str(resolved_prediction_name),
        "runtime_model_name": str(runtime_model_name),
        "model_family": str(model_family),
        "edge_capable": bool(edge_capable),
    }

    exports_out.update(calibration_info)

    if incompat_reason is not None:
        exports_out["incompatibility_reason"] = str(incompat_reason)
    if decision_threshold is not None:
        exports_out["decision_threshold"] = float(decision_threshold)
    if tflite_test_metrics is not None:
        exports_out["tflite_eval_threshold"] = float(tflite_eval_threshold)
        exports_out["tflite_test_precision"] = float(tflite_test_metrics["precision"])
        exports_out["tflite_test_recall"] = float(tflite_test_metrics["recall"])
        exports_out["tflite_test_f1"] = float(tflite_test_metrics["f1"])
        exports_out["tflite_test_pr_auc"] = float(tflite_test_metrics["pr_auc"])
        exports_out["tflite_test_fp"] = int(tflite_test_metrics["fp"])
        exports_out["tflite_test_fn"] = int(tflite_test_metrics["fn"])
    if model_size_bytes is not None:
        exports_out["model_size_bytes"] = int(model_size_bytes)
    if arena_estimated_bytes is not None:
        exports_out["arena_estimated_bytes"] = int(arena_estimated_bytes)
    if footprint_estimated_bytes is not None:
        exports_out["footprint_estimated_bytes"] = int(footprint_estimated_bytes)
    if exported_operators is not None:
        # Lista de operadores del modelo cuantizado, para que F07/F08 generen el resolver
        exports_out["operators"] = list(exported_operators)
    if quant_signature is not None:
        exports_out["input_dtype"] = quant_signature["input_dtype"]
        exports_out["output_dtype"] = quant_signature["output_dtype"]
        exports_out["input_shape"] = quant_signature["input_shape"]
        exports_out["output_shape"] = quant_signature["output_shape"]
        exports_out["input_bytes"] = quant_signature["input_bytes"]
        exports_out["output_bytes"] = quant_signature["output_bytes"]

    # ----------------------------------------------------------
    # 8. METRICS
    # ----------------------------------------------------------
    all_unsupported = set(unsupported_float) | set(unsupported_quant)
    metrics = {
        "execution_time": float(execution_time),
        "tflm_compatible": bool(edge_capable),
        "operators_detected": int(len(operators_float)),
        "unsupported_operators": int(len(all_unsupported)),
        "n_calibration_samples": int(len(df)),
        "single_input_output_int8": bool(
            quant_signature is not None
            and quant_signature["num_inputs"] == 1
            and quant_signature["num_outputs"] == 1
            and quant_signature["input_dtype"] == "int8"
            and quant_signature["output_dtype"] == "int8"
        ),
        "single_input_output_integer": bool(
            quant_signature is not None
            and quant_signature["num_inputs"] == 1
            and quant_signature["num_outputs"] == 1
            and quant_signature["input_dtype"] in {"int8", "uint8"}
            and quant_signature["output_dtype"] == "int8"
        ),
    }
    if tflite_test_metrics is not None:
        metrics.update({
            "tflite_eval_threshold": float(tflite_eval_threshold),
            "tflite_test_precision": float(tflite_test_metrics["precision"]),
            "tflite_test_recall": float(tflite_test_metrics["recall"]),
            "tflite_test_f1": float(tflite_test_metrics["f1"]),
            "tflite_test_pr_auc": float(tflite_test_metrics["pr_auc"]),
            "tflite_test_tp": int(tflite_test_metrics["tp"]),
            "tflite_test_tn": int(tflite_test_metrics["tn"]),
            "tflite_test_fp": int(tflite_test_metrics["fp"]),
            "tflite_test_fn": int(tflite_test_metrics["fn"]),
        })

    outputs = {
        "phase": PHASE,
        "variant": variant,
        "artifacts": artifacts,
        "exports": exports_out,
        "metrics": metrics,
    }

    save_outputs_yaml(variant_dir, outputs)
    validate_outputs(PHASE, outputs)

    print(f"[DONE] F06 completed — edge_capable={edge_capable}")


if __name__ == "__main__":
    main()
