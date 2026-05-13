#!/usr/bin/env bash
set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

export PYTHONPATH="${PROJECT_ROOT}"

CONFIG_PATH="${SCRIPT_DIR}/experiment.yaml"
LOG_DIR="${SCRIPT_DIR}/logs"
STATE_DIR="${SCRIPT_DIR}/state"
TIMING_DIR="${SCRIPT_DIR}/timing"

mkdir -p "$LOG_DIR" "$STATE_DIR" "$TIMING_DIR"

usage() {
    echo "Usage:"
    echo "  $0 manifest"
    echo "  $0 run_f03"
    echo "  $0 run_f04"
    echo "  $0 run_f05"
    echo "  $0 run"
    echo ""
    echo "Optional:"
    echo "  --config <path>"
    echo "  --manifest <path>"
    echo "  --fail-fast"
}

err() {
    echo -e "${RED}[ERROR] $*${NC}" >&2
}

info() {
    echo -e "${YELLOW}[INFO] $*${NC}"
}

ok() {
    echo -e "${GREEN}[OK] $*${NC}"
}

ACTION="${1:-}"
shift || true

if [[ -z "${ACTION}" ]]; then
    usage
    exit 1
fi

MANIFEST_PATH=""
FAIL_FAST=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            CONFIG_PATH="$2"
            shift 2
            ;;
        --manifest)
            MANIFEST_PATH="$2"
            shift 2
            ;;
        --fail-fast)
            FAIL_FAST=true
            shift
            ;;
        *)
            err "Unknown arg: $1"
            usage
            exit 1
            ;;
    esac
done

RUN_ID="run_$(date +%Y%m%d_%H%M%S)"
RUN_LOG_DIR="${LOG_DIR}/${RUN_ID}"
mkdir -p "$RUN_LOG_DIR"

STATE_CSV="${STATE_DIR}/${RUN_ID}.csv"
TIMING_CSV="${TIMING_DIR}/${RUN_ID}.csv"

printf 'job_id,phase,variant,status,ts_start,ts_end,exit_code,log_file\n' > "$STATE_CSV"
printf 'job_id,phase,variant,target,ts_start,ts_end,duration_s,exit_code\n' > "$TIMING_CSV"
get_band_thresholds_pct_from_f02() {
  local parent_f02="$1"

  local f02_params="executions/f02_events/${parent_f02}/params.yaml"

  if [[ -f "$f02_params" ]]; then
    python - "$f02_params" <<'PY'
import sys
from pathlib import Path
import yaml

data = yaml.safe_load(Path(sys.argv[1]).read_text(encoding="utf-8")) or {}

params = data.get("parameters", {}) if isinstance(data, dict) else {}
bands = params.get("bands") or data.get("bands") or []

if not bands:
    raise SystemExit("bands no existe en params.yaml F02")

print(" ".join(str(int(x)) for x in bands))
PY
    return 0
  fi

  err "No existe ${f02_params}"
  exit 1
}

build_prediction_name() {
  local measure="$1"
  local direction="$2"
  shift 2
  local bands=( "$@" )

  local first="${bands[0]}"
  local last="${bands[${#bands[@]}-1]}"

  if [[ "$direction" == "high" ]]; then
    echo "${measure}_any-to-${last}_100"
  elif [[ "$direction" == "low" ]]; then
    echo "${measure}_any-to-0_${first}"
  else
    echo "[ERROR] direction must be 'high' or 'low'" >&2
    return 1
  fi
}

build_objective_inline() {
  local measure="$1"
  local direction="$2"
  shift 2
  local bands=( "$@" )

  local first="${bands[0]}"
  local last="${bands[${#bands[@]}-1]}"
  local evs=()

  if [[ "$direction" == "high" ]]; then
    local prev=0
    for b in "${bands[@]}"; do
      evs+=( "${measure}_${prev}_${b}-to-${last}_100" )
      prev="$b"
    done

  elif [[ "$direction" == "low" ]]; then
    local upper=100
    for (( i=${#bands[@]}-1; i>=0; i-- )); do
      local lower="${bands[i]}"
      evs+=( "${measure}_${lower}_${upper}-to-0_${first}" )
      upper="$lower"
    done

  else
    echo "[ERROR] direction must be 'high' or 'low'" >&2
    return 1
  fi

  local joined
  joined="$(IFS=", "; echo "${evs[*]}")"
  echo "{operator: OR, events: [${joined}]}"
}

build_events_json() {
  local measure="$1"
  local direction="$2"
  shift 2
  local bands=( "$@" )

  local first="${bands[0]}"
  local last="${bands[${#bands[@]}-1]}"
  local evs=()

  if [[ "$direction" == "high" ]]; then
    local prev=0
    for b in "${bands[@]}"; do
      evs+=( "\"${measure}_${prev}_${b}-to-${last}_100\"" )
      prev="$b"
    done

  elif [[ "$direction" == "low" ]]; then
    local upper=100
    for (( i=${#bands[@]}-1; i>=0; i-- )); do
      local lower="${bands[i]}"
      evs+=( "\"${measure}_${lower}_${upper}-to-0_${first}\"" )
      upper="$lower"
    done

  else
    echo "[ERROR] direction must be 'high' or 'low'" >&2
    return 1
  fi

  local joined
  joined="$(IFS=,; echo "${evs[*]}")"
  echo "[${joined}]"
}

generate_manifest() {
    local phase_filter="$1"
    local out_manifest="${MANIFEST_DIR}/${RUN_ID}_${phase_filter}.csv"

    python "${SCRIPT_DIR}/generate_manifest.py" \
        --config "${CONFIG_PATH}" \
        --phase "${phase_filter}" \
        --output "${out_manifest}"

    echo "${out_manifest}"
}

timed_make() {
    local job_id="$1"
    local phase="$2"
    local variant="$3"
    local target="$4"
    local log_file="$5"
    shift 5

    local ts0 ts1 rc=0
    ts0="$(date +%s)"
    make "$target" "$@" >> "$log_file" 2>&1 || rc=$?
    ts1="$(date +%s)"

    printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
        "$job_id" "$phase" "$variant" "$target" "$ts0" "$ts1" "$((ts1-ts0))" "$rc" \
        >> "$TIMING_CSV"

    return $rc
}

run_manifest() {
    local manifest_csv="$1"

    info "PROJECT_ROOT=${PROJECT_ROOT}"
    info "CONFIG=${CONFIG_PATH}"
    info "MANIFEST=${manifest_csv}"
    info "LOG_DIR=${RUN_LOG_DIR}"

    cd "$PROJECT_ROOT"

    while IFS=',' read -r \
        job_id phase variant parent parent_f02 make_target script_target \
        strategy pipeline measure direction ow pw lt dedup seed \
        || [[ -n "${job_id:-}" ]]
    do
        local_log="${RUN_LOG_DIR}/${job_id}.log"
        ts0="$(date +%s)"
        ts1=""
        rc=0
        status="OK"

        echo -e "${YELLOW}[RUN] ${job_id}${NC}"

        {
            echo "job_id=${job_id}"
            echo "phase=${phase}"
            echo "variant=${variant}"
            echo "parent=${parent}"
            echo "parent_f02=${parent_f02}"
            echo "make_target=${make_target}"
            echo "script_target=${script_target}"
            echo "strategy=${strategy}"
            echo "pipeline=${pipeline}"
            echo "measure=${measure}"
            echo "ow=${ow}"
            echo "pw=${pw}"
            echo "lt=${lt}"
            echo "dedup=${dedup}"
            echo "seed=${seed}"
            echo ""
        } > "${local_log}"

        if [[ "$phase" == "f03" ]]; then
            timed_make "$job_id" "$phase" "$variant" "$make_target" "$local_log" \
                VARIANT="$variant" \
                PARENT="$parent" \
                OW="$ow" \
                PW="$pw" \
                LT="$lt" \
                STRATEGY="$strategy" \
                NAN_MODE=discard || rc=$?

            if [[ "$rc" -eq 0 ]]; then
                timed_make "$job_id" "$phase" "$variant" "$script_target" "$local_log" \
                    VARIANT="$variant" || rc=$?
            fi
        fi

        if [[ "$phase" == "f04" ]]; then
            bands_str="$(get_band_thresholds_pct_from_f02 "$parent_f02")"
            read -r -a bands <<< "$bands_str"
            target_name="$(build_prediction_name "$measure" "$direction" "${bands[@]}")"
            events_json="$(build_events_json "$measure" "$direction" "${bands[@]}")"

            {
                echo "bands=${bands_str}"
                echo "target_name=${target_name}"
                echo "events_json=${events_json}"
                echo ""
            } >> "${local_log}"

            timed_make "$job_id" "$phase" "$variant" "$make_target" "$local_log" \
                VARIANT="$variant" \
                PARENT="$parent" \
                NAME="$target_name" \
                OPERATOR=OR \
                EVENTS="$events_json" || rc=$?

            if [[ "$rc" -eq 0 ]]; then
                timed_make "$job_id" "$phase" "$variant" "$script_target" "$local_log" \
                    VARIANT="$variant" || rc=$?
            fi
        fi

        if [[ "$phase" == "f05" ]]; then
            timed_make "$job_id" "$phase" "$variant" "$make_target" "$local_log" \
                VARIANT="$variant" \
                PARENT="$parent" \
                MODEL_FAMILY=cnn1d \
                IMBALANCE_STRATEGY=rare_events \
                IMBALANCE_MAX_MAJ=20000 \
                DEDUP_MODE="$dedup" \
                SEED="$seed" || rc=$?

            if [[ "$rc" -eq 0 ]]; then
                timed_make "$job_id" "$phase" "$variant" "$script_target" "$local_log" \
                    VARIANT="$variant" || rc=$?
            fi
        fi

        ts1="$(date +%s)"
        [[ "$rc" -ne 0 ]] && status="FAIL"

        printf '%s,%s,%s,%s,%s,%s,%s,%s\n' \
            "$job_id" "$phase" "$variant" "$status" "$ts0" "$ts1" "$rc" "$local_log" \
            >> "$STATE_CSV"

        if [[ "$rc" -eq 0 ]]; then
            ok "${job_id}"
        else
            err "${job_id} -> ${local_log}"
            if [[ "$FAIL_FAST" == true ]]; then
                exit 1
            fi
        fi
    done < <( tail -n +2 "$manifest_csv" )
}

case "$ACTION" in
    manifest)
        generate_manifest all
        ;;
    run_f03)
        [[ -z "$MANIFEST_PATH" ]] && MANIFEST_PATH="$(generate_manifest f03)"
        run_manifest "$MANIFEST_PATH"
        ;;
    run_f04)
        [[ -z "$MANIFEST_PATH" ]] && MANIFEST_PATH="$(generate_manifest f04)"
        run_manifest "$MANIFEST_PATH"
        ;;
    run_f05)
        [[ -z "$MANIFEST_PATH" ]] && MANIFEST_PATH="$(generate_manifest f05)"
        run_manifest "$MANIFEST_PATH"
        ;;
    run)
        [[ -z "$MANIFEST_PATH" ]] && MANIFEST_PATH="$(generate_manifest all)"
        run_manifest "$MANIFEST_PATH"
        ;;
    *)
        err "Acción inválida: ${ACTION}"
        usage
        exit 1
        ;;
esac

# bash test/experiments/aticus/run_experiment.sh run --manifest test/experiments/aticus/manifest.csv 