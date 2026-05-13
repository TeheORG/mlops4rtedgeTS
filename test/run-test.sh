#!/bin/bash
# run-test.sh — end-to-end test and timing runner for the MLOps4OFP pipeline.
# Requires bash 3.1+.  Runs unchanged on macOS, Linux and Windows (Git Bash/WSL).
set -e

# ──────────────────────────────────────────────────────────────────────────────
#  Colour helpers
# ──────────────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

export PYTHONPATH="${PROJECT_ROOT}"

# ──────────────────────────────────────────────────────────────────────────────
#  Usage / argument parsing
# ──────────────────────────────────────────────────────────────────────────────
usage() {
    echo "Usage: $0 [--from f0N|N] [--to f0N|N]"
    echo "Examples:"
    echo "  $0"
    echo "  $0 --from f04"
    echo "  $0 --from 4"
    echo "  $0 --from 3 --to 6"
    echo "  $0 --to f05"
}

phase_to_num() {
    local raw="$1"
    raw="$(printf '%s' "$raw" | tr '[:upper:]' '[:lower:]')"
    raw="${raw#f}"
    if [[ ! "$raw" =~ ^[0-9]+$ ]]; then
        return 1
    fi
    local n=$((10#$raw))
    if (( n < 1 || n > 8 )); then
        return 1
    fi
    echo "$n"
}

START_PHASE_RAW="f01"
END_PHASE_RAW="f08"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --from|-f)
            if [[ -z "$2" ]]; then
                echo -e "${RED}[ERROR] Missing value for $1${NC}"
                usage
                exit 1
            fi
            START_PHASE_RAW="$2"
            shift 2
            ;;
        --to|-t)
            if [[ -z "$2" ]]; then
                echo -e "${RED}[ERROR] Missing value for $1${NC}"
                usage
                exit 1
            fi
            END_PHASE_RAW="$2"
            shift 2
            ;;
        --help|-h)
            usage
            exit 0
            ;;
        *)
            echo -e "${RED}[ERROR] Unknown option: $1${NC}"
            usage
            exit 1
            ;;
    esac
done

START_PHASE_NUM="$(phase_to_num "$START_PHASE_RAW")" || {
    echo -e "${RED}[ERROR] Invalid start phase: $START_PHASE_RAW. Use f01..f08 or 1..8.${NC}"
    exit 1
}
END_PHASE_NUM="$(phase_to_num "$END_PHASE_RAW")" || {
    echo -e "${RED}[ERROR] Invalid end phase: $END_PHASE_RAW. Use f01..f08 or 1..8.${NC}"
    exit 1
}
if (( START_PHASE_NUM > END_PHASE_NUM )); then
    echo -e "${RED}[ERROR] --from (${START_PHASE_NUM}) cannot be greater than --to (${END_PHASE_NUM}).${NC}"
    exit 1
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase data
# ──────────────────────────────────────────────────────────────────────────────
PHASE7_VARIANTS=(v700 v701 v702 v703 v704 v705 v706 v707 v708)
PHASE7_PARENTS=(v600 v601 v602 v603 v604 v605 v606 v607 v608)
PHASE8_PARENT_VARIANTS='[v700, v701, v702, v703, v704, v705, v706, v707, v708]'

# ──────────────────────────────────────────────────────────────────────────────
#  Timing helpers
# ──────────────────────────────────────────────────────────────────────────────
TIMING_CSV=""

# init_timing — creates a fresh CSV for this run under test/timing/.
# Columns: phase, variant, target, ts_start (epoch s), ts_end, duration_s, exit_code
init_timing() {
    local dir="${SCRIPT_DIR}/timing"
    mkdir -p "$dir"
    TIMING_CSV="${dir}/run_$(date +%s).csv"
    printf 'phase,variant,target,ts_start,ts_end,duration_s,exit_code\n' > "$TIMING_CSV"
    echo -e "${YELLOW}[TIMING] ${TIMING_CSV}${NC}"
}

# timed_make <phase> <variant> <target> [make-args ...]
# Runs "make <target> [args]", records wall-clock duration and exit code to
# TIMING_CSV, then propagates the exit code (compatible with set -e).
timed_make() {
    local ph="$1" var="$2" tgt="$3"
    shift 3
    local ts0 ts1 rc=0
    ts0="$(date +%s)"
    make "$tgt" "$@" || rc=$?
    ts1="$(date +%s)"
    printf '%s,%s,%s,%s,%s,%s,%s\n' \
        "$ph" "$var" "$tgt" "$ts0" "$ts1" "$(( ts1 - ts0 ))" "$rc" \
        >> "$TIMING_CSV"
    return $rc
}

# ──────────────────────────────────────────────────────────────────────────────
#  Helpers
# ──────────────────────────────────────────────────────────────────────────────
should_run_phase() {
    local phase_num="$1"
    (( phase_num >= START_PHASE_NUM && phase_num <= END_PHASE_NUM ))
}


# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
cd "$PROJECT_ROOT"
echo -e "${YELLOW}PROJECT_ROOT=${PROJECT_ROOT}${NC}"
echo -e "${YELLOW}PHASES=f0${START_PHASE_NUM}..f0${END_PHASE_NUM}${NC}"

init_timing

echo -e "${YELLOW}Cleaning variants from f0${END_PHASE_NUM} down to f0${START_PHASE_NUM}...${NC}"
for phase in 8 7 6 5 4 3 2 1; do
    if (( phase >= START_PHASE_NUM && phase <= END_PHASE_NUM )); then
        echo -e "${YELLOW}- remove${phase}-all${NC}"
        make "remove${phase}-all"
    fi
done

if (( START_PHASE_NUM == 1 )); then
    echo -e "${YELLOW}Running environment setup (full run from f01)...${NC}"
    make clean-setup
    make setup SETUP_CFG=setup/local.yaml
else
    echo -e "${YELLOW}Skipping setup because start phase is f0${START_PHASE_NUM} (not full run from f01).${NC}"
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 1 — Explore
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 1; then
    echo -e "${YELLOW}[TEST 1.0]${NC}"
    timed_make f01 v100 variant1 VARIANT=v100 \
        RAW=data/raw.csv \
        CLEANING=basic \
        NAN_VALUES='[-999999]'
    timed_make f01 v100 script1 VARIANT=v100
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 1.1]${NC}"
    timed_make f01 v101 variant1 VARIANT=v101 \
        RAW=data/raw.csv \
        CLEANING=basic \
        NAN_VALUES='[-999999]' \
        FIRST_LINE=1 MAX_LINES=50000
    timed_make f01 v101 script1 VARIANT=v101
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 2 — Events
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 2; then
    echo -e "${YELLOW}[TEST 2.0]${NC}"
    timed_make f02 v200 variant2 VARIANT=v200 \
        PARENT=v100 \
        BANDS="[40, 60, 80]" \
        STRATEGY=transitions \
        NAN_MODE=keep
    timed_make f02 v200 script2 VARIANT=v200
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 2.1]${NC}"
    timed_make f02 v201 variant2 VARIANT=v201 \
        PARENT=v100 \
        BANDS="[10, 20, 40, 60, 80, 90]" \
        STRATEGY=transitions \
        NAN_MODE=keep
    timed_make f02 v201 script2 VARIANT=v201
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 3 — Windows
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 3; then
    echo -e "${YELLOW}[TEST 3.0]${NC}"
    timed_make f03 v300 variant3 VARIANT=v300 \
        PARENT=v200 OW=6 LT=1 PW=1 \
        STRATEGY=synchro NAN_MODE=discard
    timed_make f03 v300 script3 VARIANT=v300
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 3.1]${NC}"
    timed_make f03 v301 variant3 VARIANT=v301 \
        PARENT=v200 OW=6 LT=1 PW=1 \
        STRATEGY=asynOW NAN_MODE=discard
    timed_make f03 v301 script3 VARIANT=v301
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 3.2]${NC}"
    timed_make f03 v302 variant3 VARIANT=v302 \
        PARENT=v201 OW=6 LT=1 PW=1 \
        STRATEGY=asynOW NAN_MODE=discard
    timed_make f03 v302 script3 VARIANT=v302
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 4 — Targets
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 4; then
    echo -e "${YELLOW}[TEST 4.0]${NC}"
    timed_make f04 v400 variant4 VARIANT=v400 \
        NAME=Battery_Active_Power_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["Battery_Active_Power_0_40-to-80_100","Battery_Active_Power_40_60-to-80_100","Battery_Active_Power_60_80-to-80_100"]'
    timed_make f04 v400 script4 VARIANT=v400
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.1]${NC}"
    timed_make f04 v401 variant4 VARIANT=v401 \
        NAME=Battery_Active_Power_Set_Response_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["Battery_Active_Power_Set_Response_0_40-to-80_100","Battery_Active_Power_Set_Response_40_60-to-80_100","Battery_Active_Power_Set_Response_60_80-to-80_100"]'
    timed_make f04 v401 script4 VARIANT=v401
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.2]${NC}"
    timed_make f04 v402 variant4 VARIANT=v402 \
        NAME=PVPCS_Active_Power_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["PVPCS_Active_Power_0_40-to-80_100","PVPCS_Active_Power_40_60-to-80_100","PVPCS_Active_Power_60_80-to-80_100"]'
    timed_make f04 v402 script4 VARIANT=v402
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.3]${NC}"
    timed_make f04 v403 variant4 VARIANT=v403 \
        NAME=GE_Active_Power_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["GE_Active_Power_0_40-to-80_100","GE_Active_Power_40_60-to-80_100","GE_Active_Power_60_80-to-80_100"]'
    timed_make f04 v403 script4 VARIANT=v403
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.4]${NC}"
    timed_make f04 v404 variant4 VARIANT=v404 \
        NAME=GE_Body_Active_Power_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["GE_Body_Active_Power_0_40-to-80_100","GE_Body_Active_Power_40_60-to-80_100","GE_Body_Active_Power_60_80-to-80_100"]'
    timed_make f04 v404 script4 VARIANT=v404
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.5]${NC}"
    timed_make f04 v405 variant4 VARIANT=v405 \
        NAME=GE_Body_Active_Power_Set_Response_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["GE_Body_Active_Power_Set_Response_0_40-to-80_100","GE_Body_Active_Power_Set_Response_40_60-to-80_100","GE_Body_Active_Power_Set_Response_60_80-to-80_100"]'
    timed_make f04 v405 script4 VARIANT=v405
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.6]${NC}"
    timed_make f04 v406 variant4 VARIANT=v406 \
        NAME=FC_Active_Power_FC_END_Set_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["FC_Active_Power_FC_END_Set_0_40-to-80_100","FC_Active_Power_FC_END_Set_40_60-to-80_100","FC_Active_Power_FC_END_Set_60_80-to-80_100"]'
    timed_make f04 v406 script4 VARIANT=v406
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.7]${NC}"
    timed_make f04 v407 variant4 VARIANT=v407 \
        NAME=FC_Active_Power_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["FC_Active_Power_0_40-to-80_100","FC_Active_Power_40_60-to-80_100","FC_Active_Power_60_80-to-80_100"]'
    timed_make f04 v407 script4 VARIANT=v407
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.8]${NC}"
    timed_make f04 v408 variant4 VARIANT=v408 \
        NAME=MG-LV-MSB_AC_Voltage_any-to-80_100 \
        PARENT=v300 OPERATOR=OR \
        EVENTS='["MG-LV-MSB_AC_Voltage_0_40-to-80_100","MG-LV-MSB_AC_Voltage_40_60-to-80_100","MG-LV-MSB_AC_Voltage_60_80-to-80_100"]'
    timed_make f04 v408 script4 VARIANT=v408
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

fi


# ──────────────────────────────────────────────────────────────────────────────
#  Phase 5 — Modeling
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 5; then
    echo -e "${YELLOW}[TEST 5.0]${NC}"
    timed_make f05 v500 variant5 VARIANT=v500 PARENT=v400 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v500 script5 VARIANT=v500
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.1]${NC}"
    timed_make f05 v501 variant5 VARIANT=v501 PARENT=v401 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v501 script5 VARIANT=v501
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.2]${NC}"
    timed_make f05 v502 variant5 VARIANT=v502 PARENT=v402 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v502 script5 VARIANT=v502
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.3]${NC}"
    timed_make f05 v503 variant5 VARIANT=v503 PARENT=v403 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v503 script5 VARIANT=v503
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.4]${NC}"
    timed_make f05 v504 variant5 VARIANT=v504 PARENT=v404 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v504 script5 VARIANT=v504
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.5]${NC}"
    timed_make f05 v505 variant5 VARIANT=v505 PARENT=v405 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v505 script5 VARIANT=v505
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.6]${NC}"
    timed_make f05 v506 variant5 VARIANT=v506 PARENT=v406 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v506 script5 VARIANT=v506
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.7]${NC}"
    timed_make f05 v507 variant5 VARIANT=v507 PARENT=v407 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v507 script5 VARIANT=v507
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.8]${NC}"
    timed_make f05 v508 variant5 VARIANT=v508 PARENT=v408 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v508 script5 VARIANT=v508
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 6 — Quantization
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 6; then
    echo -e "${YELLOW}[TEST 6.0]${NC}"
    timed_make f06 v600 variant6 VARIANT=v600 PARENT=v500
    timed_make f06 v600 script6 VARIANT=v600
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    # echo -e "${YELLOW}[TEST 6.1]${NC}"
    # timed_make f06 v601 variant6 VARIANT=v601 PARENT=v501
    # timed_make f06 v601 script6 VARIANT=v601
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.2]${NC}"
    # timed_make f06 v602 variant6 VARIANT=v602 PARENT=v502
    # timed_make f06 v602 script6 VARIANT=v602
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.3]${NC}"
    # timed_make f06 v603 variant6 VARIANT=v603 PARENT=v503
    # timed_make f06 v603 script6 VARIANT=v603
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.4]${NC}"
    # timed_make f06 v604 variant6 VARIANT=v604 PARENT=v504
    # timed_make f06 v604 script6 VARIANT=v604
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.5]${NC}"
    # timed_make f06 v605 variant6 VARIANT=v605 PARENT=v505
    # timed_make f06 v605 script6 VARIANT=v605
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.6]${NC}"
    # timed_make f06 v606 variant6 VARIANT=v606 PARENT=v506
    # timed_make f06 v606 script6 VARIANT=v606
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.7]${NC}"
    # timed_make f06 v607 variant6 VARIANT=v607 PARENT=v507
    # timed_make f06 v607 script6 VARIANT=v607
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

    # echo -e "${YELLOW}[TEST 6.8]${NC}"
    # timed_make f06 v608 variant6 VARIANT=v608 PARENT=v508
    # timed_make f06 v608 script6 VARIANT=v608
    # echo -e "${GREEN}[✓] PASSED${NC}"
    # echo ""

fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 7 — Model Validation (Edge)
#  All 9 variants follow the same skeleton: variant7 → script7.
#  script7 internally handles prepare-build, flash-run and post, including
#  graceful degradation when the parent is not edge-capable or flash-run fails.
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 7; then
    for i in "${!PHASE7_VARIANTS[@]}"; do
        echo -e "${YELLOW}[TEST 7.${i}]${NC}"
        timed_make f07 "${PHASE7_VARIANTS[$i]}" variant7 \
            VARIANT="${PHASE7_VARIANTS[$i]}" \
            PARENT="${PHASE7_PARENTS[$i]}" \
            PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01
        timed_make f07 "${PHASE7_VARIANTS[$i]}" script7 \
            VARIANT="${PHASE7_VARIANTS[$i]}"
        echo -e "${GREEN}[✓] PASSED${NC}"
        echo ""
    done
fi

# ──────────────────────────────────────────────────────────────────────────────
#  Phase 8 — System Validation (Multi-model Edge)
#  Each variant uses the same skeleton: variant8 → script8.
#  script8 internally runs select-config, then (if edge-capable) prepare-build
#  + flash-run + post, or just post when not edge-capable.
# ──────────────────────────────────────────────────────────────────────────────
if should_run_phase 8; then

    # ── TEST 8.0 — manual baseline ──────────────────────────────────────────
    echo -e "${YELLOW}[TEST 8.0 - manual baseline]${NC}"
    timed_make f08 v800 variant8 VARIANT=v800 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01
    timed_make f08 v800 script8 VARIANT=v800
    echo -e "${GREEN}[✓] PASSED v800${NC}"
    echo ""

    # ── TEST 8.1 — auto ILP (max global recall) ─────────────────────────────
    echo -e "${YELLOW}[TEST 8.1 - auto_ilp max_global_recall]${NC}"
    timed_make f08 v801 variant8 VARIANT=v801 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_global_recall
    timed_make f08 v801 script8 VARIANT=v801
    echo -e "${GREEN}[✓] PASSED v801${NC}"
    echo ""

    # ── TEST 8.2 — auto ILP (max TP) ────────────────────────────────────────
    echo -e "${YELLOW}[TEST 8.2 - auto_ilp max_tp]${NC}"
    timed_make f08 v802 variant8 VARIANT=v802 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_tp
    timed_make f08 v802 script8 VARIANT=v802
    echo -e "${GREEN}[✓] PASSED v802${NC}"
    echo ""

    # ── TEST 8.3 — auto ILP (max TP + quality filters) ──────────────────────
    echo -e "${YELLOW}[TEST 8.3 - auto_ilp max_tp + filters]${NC}"
    timed_make f08 v803 variant8 VARIANT=v803 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_tp \
        MIN_PRECISION=0.01 MIN_RECALL=0.05
    timed_make f08 v803 script8 VARIANT=v803
    echo -e "${GREEN}[✓] PASSED v803${NC}"
    echo ""

fi

echo -e "${GREEN}Run completed from f0${START_PHASE_NUM} to f08.${NC}"
echo -e "${GREEN}[TIMING] Results in ${TIMING_CSV}${NC}"