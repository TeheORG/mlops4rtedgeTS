#!/usr/bin/env python3
"""
F08 — SYSTEM VALIDATION (MULTI-MODEL EDGE) — PREPARE BUILD
"""

import argparse
import math
import shutil
from pathlib import Path

import yaml

from scripts.core.artifacts import PROJECT_ROOT, get_variant_dir
from scripts.core.edge_prepare_common import (
    compute_recommended_drain_seconds,
    compute_tu_ms,
    copy_dataset_to_csv,
    ensure_clean_dir,
    generate_memory_events_header,
    generate_runtime_config,
    generate_tflm_resolver,
    load_variant_params,
    load_yaml_file,
    resolve_platform,
    resolve_runner_dir,
    resolve_template_project_dir,
    tflites_to_models_data_c,
)


PHASE = "f08_sysval"
PARENT_PHASE = "f07_modval"

EDGE_DIR = PROJECT_ROOT / "edge"


class _NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def _yaml_dump_no_alias(data: dict) -> str:
    return yaml.dump(data, Dumper=_NoAliasDumper, sort_keys=False)


# ============================================================
# OPERATORS UNION
# ============================================================

def compute_union_operators(selected_models: list[dict]):
    ops = set()
    for m in sorted(selected_models, key=lambda x: x.get("runtime_model_name", "")):
        ops |= set(m.get("operators", []) or [])
    return sorted(ops)


# ============================================================
# MANIFEST MULTI-MODELO
# ============================================================

def build_model_manifest_multi(selected_models: list[dict]):
    manifest = []

    for idx, m in enumerate(selected_models):
        tflite_path = Path(m["model_tflite"])
        runtime_model_name = str(m["runtime_model_name"])
        threshold = float(m["threshold"])

        exec_time_ms = m.get("exec_time_ms")
        if exec_time_ms is None:
            exec_time_ms = m["ITmax"] if m.get("ITmax") is not None else m["itmax_ms"]

        itmax = int(math.ceil(float(exec_time_ms)))
        mti_ms = int(round(float(m["MTI_MS"])))
        arena_bytes = int(m["arena_bytes"])
        model_size = int(m["model_size_bytes"])
        input_bytes = int(m["input_bytes"])
        output_bytes = int(m["output_bytes"])

        manifest.append(
            {
                "id": idx,
                "name": runtime_model_name,
                "threshold": threshold,
                "itmax": itmax,
                "mti_ms": mti_ms,
                "arena_required": arena_bytes,
                "model_size_bytes": model_size,
                "input_bytes": input_bytes,
                "output_bytes": output_bytes,
                "tflite_path": str(tflite_path),
                "model_id": m.get("model_id"),
                "parent_variant": m.get("parent_variant"),
                "prediction_name": m.get("prediction_name"),
                "quality_score": m.get("quality_score"),
                "it_max_ms": m.get("it_max_ms", m.get("itmax_ms")),
                "management_overhead_ms": m.get("management_overhead_ms"),
                "exec_time_ms": m.get("exec_time_ms"),
            }
        )

    return manifest


# ============================================================
# MODEL EXECUTION PLAN
# ============================================================

def write_model_execution_plan(out_path: Path, model_manifest: list[dict], selected_models: list[dict]):
    enriched = []

    by_name = {
        str(m.get("runtime_model_name")): m
        for m in selected_models
    }

    for mm in model_manifest:
        sm = by_name.get(str(mm.get("name")), {})
        enriched.append(
            {
                "id": int(mm["id"]),
                "runtime_model_name": str(mm["name"]),
                "model_id": mm.get("model_id"),
                "parent_variant": mm.get("parent_variant"),
                "prediction_name": mm.get("prediction_name"),
                "threshold": float(mm["threshold"]),
                "exec_time_ms": float(mm["exec_time_ms"]) if mm.get("exec_time_ms") is not None else None,
                "itmax_ms": float(mm["it_max_ms"]) if mm.get("it_max_ms") is not None else None,
                "management_overhead_ms": float(mm["management_overhead_ms"]) if mm.get("management_overhead_ms") is not None else None,
                "mti_ms": int(mm["mti_ms"]),
                "arena_required": int(mm["arena_required"]),
                "model_size_bytes": int(mm["model_size_bytes"]),
                "input_bytes": int(mm["input_bytes"]),
                "output_bytes": int(mm["output_bytes"]),
                "model_tflite": sm.get("model_tflite"),
                "evaluation_dataset_csv": sm.get("evaluation_dataset_csv"),
                "operators": list(sm.get("operators", []) or []),
                "quality_score": sm.get("quality_score"),
            }
        )

    payload = {
        "phase": PHASE,
        "models": enriched,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_yaml_dump_no_alias(payload))


# ============================================================
# SYSTEM PROFILE
# ============================================================

def write_initial_system_profile(
    out_path: Path,
    *,
    phase: str,
    variant: str,
    parent_phase: str,
    parent_variants: list[str],
    platform: str,
    selected_variants: list[str],
    compatible_input_signature: bool,
    configuration_edge_capable: bool,
    system_viable: bool,
    exec_time_policy: str,
    unique_windows_count: int,
    duplicate_windows_removed: int,
    max_exec_time_ms: float,
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
    operators_union: list[str],
    required_arena_bytes: int,
    total_model_size_bytes: int,
    total_models_declared: int,
    total_models_selected: int,
    MTI_MS: int,
    memory_check: dict,
    edge_run_config_path: Path,
    unique_windows_path: Path,
    input_dataset_csv_path: Path,
    edge_project_dir: Path,
    selected_models: list[dict],
):
    profile = {
        "phase": phase,
        "variant": variant,
        "parent": {
            "phase": parent_phase,
            "variants": parent_variants,
        },
        "selection": {
            "selected_variants": selected_variants,
        },
        "system": {
            "platform": platform,
            "compatible_input_signature": bool(compatible_input_signature),
            "configuration_edge_capable": bool(configuration_edge_capable),
            "system_viable": bool(system_viable),
        },
        "execution_policy": {
            "exec_time_policy": exec_time_policy,
            "max_exec_time_ms": float(max_exec_time_ms),
            "MTI_MS": int(MTI_MS),
        },
        "datasets": {
            "unique_windows_csv": str(unique_windows_path),
            "input_dataset_csv": str(input_dataset_csv_path),
            "unique_windows_count": int(unique_windows_count),
            "duplicate_windows_removed": int(duplicate_windows_removed),
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
            "operators_union": list(operators_union),
            "required_arena_bytes": int(required_arena_bytes),
            "total_model_size_bytes": int(total_model_size_bytes),
            "total_models_declared": int(total_models_declared),
            "total_models_selected": int(total_models_selected),
        },
        "memory_check": dict(memory_check or {}),
        "models": [
            {
                "parent_variant": m["parent_variant"],
                "model_id": m["model_id"],
                "runtime_model_name": m["runtime_model_name"],
                "prediction_name": m["prediction_name"],
                "quality_score": m.get("quality_score"),
                "threshold": float(m["threshold"]),
                "itmax_ms": float(m["itmax_ms"]),
                "it_max_ms": float(m.get("it_max_ms", m["itmax_ms"])),
                "management_overhead_ms": float(m.get("management_overhead_ms", 0.0)),
                "exec_time_ms": float(m.get("exec_time_ms", m["itmax_ms"])),
                "ITmax": int(m["ITmax"]) if m.get("ITmax") is not None else None,
                "MTI_MS": int(m["MTI_MS"]),
                "arena_bytes": int(m["arena_bytes"]),
                "model_size_bytes": int(m["model_size_bytes"]),
                "input_bytes": int(m["input_bytes"]),
                "output_bytes": int(m["output_bytes"]),
                "operators": list(m.get("operators", []) or []),
                "model_tflite": str(m["model_tflite"]),
                "evaluation_dataset_csv": str(m.get("evaluation_dataset_csv")),
            }
            for m in selected_models
        ],
        "run": {
            "edge_run_completed": False,
        },
        "artifacts": {
            "edge_run_config": str(edge_run_config_path),
            "unique_windows": str(unique_windows_path),
            "input_dataset_csv": str(input_dataset_csv_path),
            "edge_project_dir": str(edge_project_dir),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_yaml_dump_no_alias(profile))


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--variant", required=True)
    args = parser.parse_args()

    variant = args.variant
    params_data = load_variant_params(get_variant_dir, PHASE, variant, "F08")
    params = params_data.get("parameters", {})

    platform = resolve_platform(params, "F08")

    try:
        time_scale = float(params.get("time_scale_factor", 1.0))
    except Exception:
        raise RuntimeError("[F08] time_scale_factor debe ser numérico")
    if time_scale <= 0:
        raise RuntimeError("[F08] time_scale_factor debe ser > 0")

    max_rows = params.get("max_rows")

    variant_dir = get_variant_dir(PHASE, variant)
    selected_cfg_path = variant_dir / "08_selected_configuration.yaml"
    selected_cfg = load_yaml_file(selected_cfg_path, "08_selected_configuration.yaml", "F08")

    selection_mode = str(selected_cfg.get("selection_mode", "")).strip().lower()
    if selection_mode not in {"manual", "auto_ilp"}:
        raise RuntimeError(f"[F08] selection_mode no soportado en F082: {selection_mode}")

    if not bool(selected_cfg.get("selection_completed", False)):
        raise RuntimeError("[F08] selected_configuration incompleta")

    if not bool(selected_cfg.get("configuration_edge_capable", False)):
        raise RuntimeError(
            "[F08] Configuración inviable: edge_capable=false. "
            "No se genera proyecto edge ni se debe ejecutar flash-run."
        )

    if str(selected_cfg.get("platform", "")).strip().lower() != platform:
        raise RuntimeError("[F08] platform inconsistente entre params y 08_selected_configuration.yaml")

    template_project_dir = resolve_template_project_dir(EDGE_DIR, platform, "F08")
    runner_dir = resolve_runner_dir(EDGE_DIR, platform)

    common_sig = selected_cfg.get("common_input_signature", {}) or {}
    aggregates = selected_cfg.get("aggregates", {}) or {}
    limits = selected_cfg.get("system_limits", {}) or {}
    memory_check = selected_cfg.get("memory_check", {}) or {}
    datasets = selected_cfg.get("datasets", {}) or {}
    selected_models = selected_cfg.get("models", []) or []
    parent_info = selected_cfg.get("parent", {}) or {}

    total_models_selected_cfg = int(aggregates.get("total_models_selected", len(selected_models)) or 0)

    if not bool(selected_cfg.get("system_viable", False)) or total_models_selected_cfg <= 0 or not selected_models:
        raise RuntimeError(
            "[F08] Configuración inviable: 0 modelos seleccionados o sistema no viable. "
            "No se genera proyecto edge ni se debe ejecutar flash-run."
        )

    Tu = int(common_sig["Tu"])
    OW = int(common_sig["OW"])
    LT = int(common_sig["LT"])
    PW = int(common_sig["PW"])
    event_type_count = int(common_sig["event_type_count"])

    input_dtype = common_sig.get("input_dtype")
    output_dtype = common_sig.get("output_dtype")
    input_shape = common_sig.get("input_shape")
    output_shape = common_sig.get("output_shape")
    input_bytes = int(common_sig["input_bytes"])
    output_bytes = int(common_sig["output_bytes"])

    if input_dtype not in {"int8", "uint8"}:
        raise RuntimeError(f"[F08] Modelo incompatible: input_dtype={input_dtype}")

    if output_dtype != "int8":
        raise RuntimeError(f"[F08] Modelo incompatible: output_dtype={output_dtype}")

    if input_bytes <= 0 or output_bytes <= 0:
        raise RuntimeError("[F08] input/output bytes inválidos")

    operators = compute_union_operators(selected_models)
    required_arena_bytes = int(aggregates["required_arena_bytes"])
    total_model_size_bytes = int(aggregates["total_model_size_bytes"])
    total_models_declared = int(aggregates["total_models_declared"])
    total_models_selected = int(aggregates["total_models_selected"])
    global_mti_ms = int(limits["MTI_MS"])

    unique_windows_count = int(aggregates.get("unique_windows_count", 0))
    duplicate_windows_removed = int(aggregates.get("duplicate_windows_removed", 0))
    max_exec_time_ms = float(aggregates.get("max_exec_time_ms", 0.0))
    exec_time_policy = str(selected_cfg.get("exec_time_policy", ""))

    if selected_cfg.get("time_scale_factor") is not None:
        try:
            time_scale = float(selected_cfg.get("time_scale_factor"))
        except Exception:
            raise RuntimeError("[F08] time_scale_factor (selección) debe ser numérico")
        if time_scale <= 0:
            raise RuntimeError("[F08] time_scale_factor (selección) debe ser > 0")

    tu_ms = compute_tu_ms(Tu, time_scale)

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

    model_manifest = build_model_manifest_multi(selected_models)

    models_data_path = build_gen / "models_data.c"
    tflites_to_models_data_c(model_manifest, models_data_path, "F08")

    resolver_path = edge_project_dir / "main" / "model_resolver.h"
    resolver_path.parent.mkdir(parents=True, exist_ok=True)
    generate_tflm_resolver(operators, resolver_path, "F08")

    runtime_cfg = build_gen / "config.h"
    generate_runtime_config(runtime_cfg, OW, global_mti_ms, tu_ms)

    unique_windows_rel = datasets.get("unique_windows_csv")
    if not unique_windows_rel:
        raise RuntimeError("[F08] datasets.unique_windows_csv no definido en 08_selected_configuration.yaml")

    reference_dataset = Path(unique_windows_rel)
    if not reference_dataset.is_absolute():
        reference_dataset = (PROJECT_ROOT / reference_dataset).resolve()

    if not reference_dataset.exists():
        raise RuntimeError(f"[F08] Dataset de ventanas únicas no encontrado: {reference_dataset}")

    csv_variant = variant_dir / "08_input_dataset.csv"
    csv_project = edge_project_dir / "data" / "input_dataset.csv"

    copy_dataset_to_csv(reference_dataset, csv_variant, csv_project, allow_csv=True)

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
        "selection_mode": selected_cfg.get("selection_mode"),
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
            "PW": PW,
        },
        "events": {
            "event_type_count": int(event_type_count),
        },
        "drain": {
            "tu_ms": float(tu_ms),
            "recommended_drain_seconds": float(recommended_drain_seconds),
        },
        "memory": {
            "arena_per_model_max": required_arena_bytes,
            "arena_global": int(float(required_arena_bytes) * 1.15) + 1024,
            "model_memory_payload_bytes": memory_check.get("model_memory_payload_bytes"),
            "model_memory_required_bytes": memory_check.get("model_memory_required_bytes"),
            "memory_guard_bytes": memory_check.get("memory_guard_bytes"),
            "plate_available_heap_bytes": memory_check.get("plate_available_heap_bytes"),
            "fit_margin_bytes": memory_check.get("fit_margin_bytes"),
            "fits": memory_check.get("fits"),
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
                "model_id": m.get("model_id"),
                "parent_variant": m.get("parent_variant"),
                "prediction_name": m.get("prediction_name"),
                "exec_time_ms": float(m["exec_time_ms"]) if m.get("exec_time_ms") is not None else None,
            }
            for m in model_manifest
        ],
        "operators": operators,
        "limits": {
            "MTI_MS": int(global_mti_ms),
            "ITmax": max(int(m["itmax"]) for m in model_manifest),
        },
        "dataset": {
            "source_unique_windows_csv": str(reference_dataset),
            "max_rows": int(max_rows) if max_rows is not None else None,
            "unique_windows_count": int(unique_windows_count),
        },
    }

    out_cfg = variant_dir / "08_edge_run_config.yaml"
    out_cfg.write_text(_yaml_dump_no_alias(edge_cfg_yaml))

    model_execution_plan_path = variant_dir / "08_model_execution_plan.yaml"
    write_model_execution_plan(model_execution_plan_path, model_manifest, selected_models)

    system_profile_path = variant_dir / "08_system_profile.yaml"
    write_initial_system_profile(
        system_profile_path,
        phase=PHASE,
        variant=variant,
        parent_phase=PARENT_PHASE,
        parent_variants=list(parent_info.get("variants", []) or []),
        platform=platform,
        selected_variants=list(selected_cfg.get("selected_variants", []) or []),
        compatible_input_signature=bool(selected_cfg.get("compatible_input_signature", False)),
        configuration_edge_capable=bool(selected_cfg.get("configuration_edge_capable", False)),
        system_viable=bool(selected_cfg.get("system_viable", False)),
        exec_time_policy=exec_time_policy,
        unique_windows_count=unique_windows_count,
        duplicate_windows_removed=duplicate_windows_removed,
        max_exec_time_ms=max_exec_time_ms,
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
        operators_union=operators,
        required_arena_bytes=required_arena_bytes,
        total_model_size_bytes=total_model_size_bytes,
        total_models_declared=total_models_declared,
        total_models_selected=total_models_selected,
        MTI_MS=global_mti_ms,
        memory_check=memory_check,
        edge_run_config_path=out_cfg,
        unique_windows_path=reference_dataset,
        input_dataset_csv_path=csv_variant,
        edge_project_dir=edge_project_dir,
        selected_models=selected_models,
    )

    print(f"[F08] preparebuild OK — {variant}")
    print(f"[F08] Platform: {platform}")
    print(f"[F08] Models configured: {len(model_manifest)}")
    print(f"[F08] Unique windows: {unique_windows_count}")
    print(f"[F08] Required arena: {required_arena_bytes} bytes")
    print(f"[F08] Total model size: {total_model_size_bytes} bytes")
    if memory_check:
        print(
            "[F08] Memory check: "
            f"required={memory_check.get('model_memory_required_bytes')} B, "
            f"available={memory_check.get('plate_available_heap_bytes')} B, "
            f"margin={memory_check.get('fit_margin_bytes')} B"
        )
    print(f"[F08] Operators: {len(operators)}")
    print(f"[F08] Input bytes: {input_bytes}")
    print(f"[F08] Output bytes: {output_bytes}")


if __name__ == "__main__":
    main()