#!/usr/bin/env python3
"""
F07 — MODEL VALIDATION (EDGE) — PREPARE BUILD
"""

import argparse
import shutil
from pathlib import Path

import yaml

from scripts.core.artifacts import PROJECT_ROOT, get_variant_dir
from scripts.core.edge_prepare_common import (
    compute_recommended_drain_seconds,
    compute_tu_ms,
    copy_or_convert_dataset_to_csv,
    copy_dataset_to_csv,
    ensure_clean_dir,
    generate_memory_events_header,
    generate_runtime_config,
    generate_tflm_resolver,
    load_phase_outputs,
    load_variant_params,
    resolve_platform,
    resolve_runner_dir,
    resolve_template_project_dir,
    tflites_to_models_data_c,
)


PHASE = "f07_modval"
PARENT_PHASE = "f06_quant"

EDGE_DIR = PROJECT_ROOT / "edge"


# ============================================================
# OPERATORS UNION
# ============================================================

def compute_union_operators(exports_list):

    ops = set()

    for exp in sorted(exports_list, key=lambda x: x.get("prediction_name", "")):
        ops |= set(exp.get("operators", []))

    return sorted(ops)


def build_model_manifest_single(
    tflite_path: Path,
    prediction_name: str,
    threshold: float,
    itmax: int,
    mti_ms: float,
    arena_bytes: int,
    model_size: int,
    input_bytes: int,
    output_bytes: int,
):
    # Contrato multi-modelo: aunque hoy haya un modelo, se serializa como lista.
    return [
        {
            "id": 0,
            "name": str(prediction_name),
            "threshold": float(threshold),
            "itmax": int(itmax),
            "mti_ms": int(round(float(mti_ms))),
            "arena_required": int(arena_bytes),
            "model_size_bytes": int(model_size),
            "input_bytes": int(input_bytes),
            "output_bytes": int(output_bytes),
            "tflite_path": str(tflite_path),
        }
    ]


def write_initial_model_profile(
    out_path: Path,
    *,
    phase: str,
    variant: str,
    parent_phase: str,
    parent_variant: str,
    model_id: str,
    runtime_model_name: str,
    prediction_name: str,
    platform: str,
    edge_capable: bool,
    incompatibility_reason: str | None,
    Tu: int,
    OW: int,
    LT: int,
    PW: int,
    event_type_count: int,
    input_dtype: str,
    output_dtype: str,
    input_shape,
    output_shape,
    input_bytes: int,
    output_bytes: int,
    operators: list[str],
    decision_threshold: float,
    arena_bytes: int,
    arena_global_bytes: int,
    model_size_bytes: int,
    MTI_MS: int,
    ITmax: int,
    itmax_ms: float,
    edge_run_config_path: Path,
    input_dataset_csv_path: Path,
    evaluation_dataset_csv_path: Path,
    model_tflite_path: Path,
):
    profile = {
        "phase": phase,
        "variant": variant,
        "parent": {
            "phase": parent_phase,
            "variant": parent_variant,
        },
        "model": {
            "model_id": model_id,
            "runtime_model_name": runtime_model_name,
            "prediction_name": prediction_name,
            "platform": platform,
        },
        "compatibility": {
            "edge_capable": bool(edge_capable),
            "incompatibility_reason": incompatibility_reason,
        },
        "input_signature": {
            "Tu": int(Tu),
            "OW": int(OW),
            "LT": int(LT),
            "PW": int(PW),
            "event_type_count": int(event_type_count),
            "input_dtype": input_dtype,
            "output_dtype": output_dtype,
            "input_shape": input_shape,
            "output_shape": output_shape,
            "input_bytes": int(input_bytes),
            "output_bytes": int(output_bytes),
        },
        "build": {
            "operators": list(operators),
            "decision_threshold": float(decision_threshold),
            "arena_bytes": int(arena_bytes),
            "arena_global_bytes": int(arena_global_bytes),
            "model_size_bytes": int(model_size_bytes),
        },
        "limits": {
            "MTI_MS": int(MTI_MS),
            "ITmax": int(ITmax),
            "itmax_ms": float(itmax_ms),
        },
        "run": {
            "edge_run_completed": False,
        },
        "artifacts": {
            "edge_run_config": str(edge_run_config_path),
            "input_dataset_csv": str(input_dataset_csv_path),
            "evaluation_dataset_csv": str(evaluation_dataset_csv_path),
            "model_tflite": str(model_tflite_path),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml.safe_dump(profile, sort_keys=False))

# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant

    params_data = load_variant_params(get_variant_dir, PHASE, variant, "F07")
    params = params_data.get("parameters", {})

    time_scale = float(params.get("time_scale_factor", 1.0))

    parent_variant = params_data.get("parent")

    if not parent_variant:
        raise RuntimeError("parent variant requerido")

    mti_ms = params.get("MTI_MS")
    legacy_mti = params.get("MTI")
    ITmax = params.get("ITmax")
    max_rows = params.get("max_rows")

    platform = resolve_platform(params, "F07")
    template_project_dir = resolve_template_project_dir(EDGE_DIR, platform, "F07")
    runner_dir = resolve_runner_dir(EDGE_DIR, platform)

    f06_outputs, f06_dir = load_phase_outputs(PROJECT_ROOT, PARENT_PHASE, parent_variant, "F07")

    exports = f06_outputs["exports"]
    artifacts = f06_outputs["artifacts"]

    edge_capable = bool(exports.get("edge_capable", False))
    incompat_reason = exports.get("incompatibility_reason")

    if not edge_capable:
        details = f" Razón: {incompat_reason}." if incompat_reason else ""
        raise RuntimeError(
            "Modelo no edge_capable según F06. "
            "No se puede preparar F07 para ejecución en edge." + details
        )

    input_dtype = exports.get("input_dtype")
    output_dtype = exports.get("output_dtype")

    input_bytes = exports.get("input_bytes")
    output_bytes = exports.get("output_bytes")

    input_shape = exports.get("input_shape")
    output_shape = exports.get("output_shape")

    arena_bytes = exports.get("arena_estimated_bytes")
    if arena_bytes is None:
        raise RuntimeError("arena_estimated_bytes missing en F06 exports")

    arena_global = int(float(arena_bytes) * 1.15) + 1024
    model_size = exports.get("model_size_bytes")

    if input_dtype not in {"int8", "uint8"}:
        raise RuntimeError(f"Modelo incompatible: input_dtype={input_dtype}")

    if output_dtype != "int8":
        raise RuntimeError(f"Modelo incompatible: output_dtype={output_dtype}")

    if input_bytes is None or input_bytes <= 0:
        raise RuntimeError("input_bytes inválido")

    if output_bytes is None or output_bytes <= 0:
        raise RuntimeError("output_bytes inválido")
    
    if arena_global is None or arena_global <= 0:
        raise RuntimeError("Invalid arena_global")
    
    operators = exports.get("operators")

    if not operators:
        raise RuntimeError("Operators list missing in exports")

    if not isinstance(operators, list):
        raise RuntimeError("Operators must be a list")

    operators = compute_union_operators([exports])

    event_type_count = exports.get("event_type_count")
    if event_type_count is None:
        raise RuntimeError(
            "event_type_count missing in F06 exports. "
            "Regenera F03->F06 con el pipeline actualizado antes de preparar F07."
        )
    event_type_count = int(event_type_count)
    if event_type_count > 256:
        raise RuntimeError(
            f"event_type_count={event_type_count} exceeds uint8 capacity (256)."
        )

    Tu = exports["Tu"]
    OW = exports["OW"]
    LT = exports["LT"]
    PW = exports["PW"]

    prediction_name = exports["prediction_name"]
    runtime_model_name = exports.get("runtime_model_name")
    if not runtime_model_name:
        raise RuntimeError(
            "runtime_model_name missing in F06 exports. "
            "Regenera F06 con el pipeline actualizado antes de preparar F07."
        )
    model_id = f"{runtime_model_name}__{platform}"
    threshold = exports.get("decision_threshold")

    if threshold is None:
        raise RuntimeError("decision_threshold missing")

    if not (0 <= threshold <= 1):
        raise RuntimeError("decision_threshold out of range")
    
    arena_bytes = int(float(arena_bytes))

    if mti_ms is None:
        if legacy_mti is not None:
            # Legacy fallback: MTI venia en unidades Tu
            mti_ms = float(legacy_mti) * float(compute_tu_ms(Tu, time_scale))
        else:
            raise RuntimeError("MTI_MS requerido (milisegundos). Define MTI_MS en make variant7")

    if ITmax is None:
        ITmax = int(round(float(mti_ms)))

    tu_ms = compute_tu_ms(Tu, time_scale)

    variant_dir = get_variant_dir(PHASE, variant)
    project_dir_name = f"{platform}_project"
    edge_project_dir = variant_dir / project_dir_name

    ensure_clean_dir(edge_project_dir)

    shutil.copytree(
        template_project_dir,
        edge_project_dir,
        dirs_exist_ok=True,
    )

    runner_dir_name = None
    if runner_dir is not None:
        runner_dir_name = f"{platform}_runner"
        runner_dst = variant_dir / runner_dir_name
        ensure_clean_dir(runner_dst)
        shutil.copytree(
            runner_dir,
            runner_dst,
            dirs_exist_ok=True,
        )

    build_gen = edge_project_dir / "build_generated"

    tflite_path = f06_dir / artifacts["model_tflite"]["path"]
    calib_path = f06_dir / artifacts["calibration_dataset"]["path"]

    if not tflite_path.exists():
        raise RuntimeError("TFLite model missing")

    if tflite_path.stat().st_size != model_size:
        raise RuntimeError("Model size mismatch")    

    models_data_path = build_gen / "models_data.c"

    model_manifest = build_model_manifest_single(
        tflite_path=tflite_path,
        prediction_name=runtime_model_name,
        threshold=threshold,
        itmax=ITmax,
        mti_ms=mti_ms,
        arena_bytes=arena_bytes,
        model_size=model_size,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
    )

    # config.h define límites globales de sistema; se derivan del conjunto de modelos.
    global_mti_ms = max(int(m["mti_ms"]) for m in model_manifest)
    global_itmax = max(int(m["itmax"]) for m in model_manifest)

    tflites_to_models_data_c(
        model_manifest,
        models_data_path,
        "F07",
    )

    resolver_path = edge_project_dir / "main" / "model_resolver.h"
    resolver_path.parent.mkdir(parents=True, exist_ok=True)

    generate_tflm_resolver(operators, resolver_path, "F07")

    runtime_cfg = build_gen / "config.h"

    generate_runtime_config(
        runtime_cfg,
        OW,
        global_mti_ms,
        tu_ms,
    )

    csv_variant = variant_dir / "07_input_dataset.csv"
    csv_project = edge_project_dir / "data" / "input_dataset.csv"

    copy_dataset_to_csv(calib_path, csv_variant, csv_project, allow_csv=False)

    evaluation_dataset_variant = variant_dir / "07_evaluation_dataset.csv"
    copy_or_convert_dataset_to_csv(
        calib_path,
        evaluation_dataset_variant,
        allow_csv=True,
    )

    memory_events_path = build_gen / "memory_events.h"
    if max_rows is not None:
        max_rows = int(max_rows)
        if max_rows < 1:
            raise RuntimeError("max_rows must be >= 1 when provided")
    generate_memory_events_header(
        csv_variant,
        memory_events_path,
        event_type_count=event_type_count,
        max_rows=max_rows,
    )

    recommended_drain_seconds = compute_recommended_drain_seconds(
        OW,
        LT,
        tu_ms,
        global_mti_ms,
    )

    edge_cfg_yaml = {

        "phase": PHASE,
        "variant": variant,
        "platform": platform,
        "execution": {
            "project_dir": project_dir_name,
            "runner_dir": runner_dir_name,
        },

        "time_scale_factor": time_scale,

        "geometry": {
            "Tu_dataset": Tu,
            "Tu_edge_ms": tu_ms,
            "OW": OW,
            "LT": LT,
            "PW": PW
        },

        "events": {
            "event_type_count": int(event_type_count)
        },

        # Parametros host-side para envio serie y drenado final.
        "drain": {
            "tu_ms": float(tu_ms),
            "recommended_drain_seconds": float(recommended_drain_seconds)
        },

        "memory": {
            "arena_per_model": arena_bytes,
            "arena_global": arena_global
        },

        "models": [
            {
                "id": int(m["id"]),
                "name": str(m["name"]),
                "threshold": float(m["threshold"]),
                "itmax": int(m["itmax"]),
                "mti_ms": int(m["mti_ms"]),
                "arena_required": int(m["arena_required"]),
                "model_size_bytes": int(m["model_size_bytes"]),
                "input_bytes": int(m["input_bytes"]),
                "output_bytes": int(m["output_bytes"]),
            }
            for m in model_manifest
        ],

        # Compatibilidad temporal con consumidores legacy monomodelo.
        "prediction": {
            "name": runtime_model_name,
            "threshold": threshold
        },

        "operators": operators,

        "limits": {
            "MTI_MS": int(global_mti_ms),
            "ITmax": int(global_itmax)
        },
        "dataset": {
            "max_rows": int(max_rows) if max_rows is not None else None
        },
    }

    out_cfg = variant_dir / "07_edge_run_config.yaml"

    out_cfg.write_text(
        yaml.safe_dump(edge_cfg_yaml, sort_keys=False)
    )

    model_profile_path = variant_dir / "07_model_profile.yaml"

    write_initial_model_profile(
        model_profile_path,
        phase=PHASE,
        variant=variant,
        parent_phase=PARENT_PHASE,
        parent_variant=parent_variant,
        model_id=model_id,
        runtime_model_name=runtime_model_name,
        prediction_name=prediction_name,
        platform=platform,
        edge_capable=edge_capable,
        incompatibility_reason=incompat_reason,
        Tu=Tu,
        OW=OW,
        LT=LT,
        PW=PW,
        event_type_count=event_type_count,
        input_dtype=input_dtype,
        output_dtype=output_dtype,
        input_shape=input_shape,
        output_shape=output_shape,
        input_bytes=input_bytes,
        output_bytes=output_bytes,
        operators=operators,
        decision_threshold=threshold,
        arena_bytes=arena_bytes,
        arena_global_bytes=arena_global,
        model_size_bytes=model_size,
        MTI_MS=int(global_mti_ms),
        ITmax=int(global_itmax),
        itmax_ms=float(global_itmax),
        edge_run_config_path=out_cfg,
        input_dataset_csv_path=csv_variant,
        evaluation_dataset_csv_path=evaluation_dataset_variant,
        model_tflite_path=tflite_path,
    )
    
    print(f"[F07] preparebuild OK — {variant}")
    print(f"[F07] Platform: {platform}")
    print(f"[F07] Model size: {model_size} bytes")
    print(f"[F07] Arena estimated: {arena_bytes} bytes")
    print(f"[F07] Operators: {len(operators)}")
    print(f"[F07] Models configured: {len(model_manifest)}")
    print(f"[F07] Input bytes: {input_bytes}")
    print(f"[F07] Output bytes: {output_bytes}")


if __name__ == "__main__":
    main()