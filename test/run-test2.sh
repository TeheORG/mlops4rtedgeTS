#!/bin/bash
# run-test2.sh — end-to-end runner para un árbol paralelo de variantes.
# Genera/ejecuta variantes vP1N a partir del árbol existente vP0N, manteniendo
# intactas las ejecuciones originales de run-test.sh.
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

parallel_variant() {
    local variant="$1"
    if [[ ! "$variant" =~ ^v([1-8])0([0-9])$ ]]; then
        echo "[ERROR] Variant fuera del patrón paralelo esperado: ${variant}" >&2
        return 1
    fi
    echo "v${BASH_REMATCH[1]}1${BASH_REMATCH[2]}"
}

phase_dir_name() {
    case "$1" in
        1) echo "f01_explore" ;;
        2) echo "f02_events" ;;
        3) echo "f03_windows" ;;
        4) echo "f04_targets" ;;
        5) echo "f05_modeling" ;;
        6) echo "f06_quant" ;;
        7) echo "f07_modval" ;;
        8) echo "f08_sysval" ;;
        *) return 1 ;;
    esac
}

variant_exists() {
    local phase_num="$1"
    local variant="$2"
    local phase_dir
    phase_dir="$(phase_dir_name "$phase_num")" || return 1
    [[ -d "${PROJECT_ROOT}/executions/${phase_dir}/${variant}" ]]
}

remove_parallel_variant_if_exists() {
    local phase_num="$1"
    local variant="$2"
    if variant_exists "$phase_num" "$variant"; then
        echo -e "${YELLOW}- remove${phase_num} ${variant}${NC}"
        make "remove${phase_num}" VARIANT="${variant}"
    fi
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
PHASE1_VARIANTS=(v110 v111)
PHASE2_VARIANTS=(v210 v211)
PHASE3_VARIANTS=(v310 v311 v312)
PHASE4_VARIANTS=(v410 v411 v412 v413 v414 v415 v416 v417 v418)
PHASE5_VARIANTS=(v510 v511 v512 v513 v514 v515 v516 v517 v518)
PHASE6_VARIANTS=(v610 v611 v612 v613 v614 v615 v616 v617 v618)
PHASE7_VARIANTS=(v710 v711 v712 v713 v714 v715 v716 v717 v718)
PHASE7_PARENTS=(v610 v611 v612 v613 v614 v615 v616 v617 v618)
PHASE8_PARENT_VARIANTS='[v710, v711, v712, v713, v714, v715, v716, v717, v718]'

# ──────────────────────────────────────────────────────────────────────────────
#  Timing helpers
# ──────────────────────────────────────────────────────────────────────────────
TIMING_CSV=""

init_timing() {
    local dir="${SCRIPT_DIR}/timing"
    mkdir -p "$dir"
    TIMING_CSV="${dir}/run2_$(date +%s).csv"
    printf 'phase,variant,target,ts_start,ts_end,duration_s,exit_code\n' > "$TIMING_CSV"
    echo -e "${YELLOW}[TIMING] ${TIMING_CSV}${NC}"
}

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

should_run_phase() {
    local phase_num="$1"
    (( phase_num >= START_PHASE_NUM && phase_num <= END_PHASE_NUM ))
}

cleanup_parallel_tree() {
    echo -e "${YELLOW}Cleaning only parallel variants from f0${END_PHASE_NUM} down to f0${START_PHASE_NUM}...${NC}"
    if (( 8 >= START_PHASE_NUM && 8 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 8 v813
        remove_parallel_variant_if_exists 8 v812
        remove_parallel_variant_if_exists 8 v811
        remove_parallel_variant_if_exists 8 v810
    fi
    if (( 7 >= START_PHASE_NUM && 7 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 7 v718
        remove_parallel_variant_if_exists 7 v717
        remove_parallel_variant_if_exists 7 v716
        remove_parallel_variant_if_exists 7 v715
        remove_parallel_variant_if_exists 7 v714
        remove_parallel_variant_if_exists 7 v713
        remove_parallel_variant_if_exists 7 v712
        remove_parallel_variant_if_exists 7 v711
        remove_parallel_variant_if_exists 7 v710
    fi
    if (( 6 >= START_PHASE_NUM && 6 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 6 v618
        remove_parallel_variant_if_exists 6 v617
        remove_parallel_variant_if_exists 6 v616
        remove_parallel_variant_if_exists 6 v615
        remove_parallel_variant_if_exists 6 v614
        remove_parallel_variant_if_exists 6 v613
        remove_parallel_variant_if_exists 6 v612
        remove_parallel_variant_if_exists 6 v611
        remove_parallel_variant_if_exists 6 v610
    fi
    if (( 5 >= START_PHASE_NUM && 5 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 5 v518
        remove_parallel_variant_if_exists 5 v517
        remove_parallel_variant_if_exists 5 v516
        remove_parallel_variant_if_exists 5 v515
        remove_parallel_variant_if_exists 5 v514
        remove_parallel_variant_if_exists 5 v513
        remove_parallel_variant_if_exists 5 v512
        remove_parallel_variant_if_exists 5 v511
        remove_parallel_variant_if_exists 5 v510
    fi
    if (( 4 >= START_PHASE_NUM && 4 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 4 v418
        remove_parallel_variant_if_exists 4 v417
        remove_parallel_variant_if_exists 4 v416
        remove_parallel_variant_if_exists 4 v415
        remove_parallel_variant_if_exists 4 v414
        remove_parallel_variant_if_exists 4 v413
        remove_parallel_variant_if_exists 4 v412
        remove_parallel_variant_if_exists 4 v411
        remove_parallel_variant_if_exists 4 v410
    fi
    if (( 3 >= START_PHASE_NUM && 3 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 3 v312
        remove_parallel_variant_if_exists 3 v311
        remove_parallel_variant_if_exists 3 v310
    fi
    if (( 2 >= START_PHASE_NUM && 2 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 2 v211
        remove_parallel_variant_if_exists 2 v210
    fi
    if (( 1 >= START_PHASE_NUM && 1 <= END_PHASE_NUM )); then
        remove_parallel_variant_if_exists 1 v111
        remove_parallel_variant_if_exists 1 v110
    fi
}

# ──────────────────────────────────────────────────────────────────────────────
#  Main
# ──────────────────────────────────────────────────────────────────────────────
cd "$PROJECT_ROOT"
echo -e "${YELLOW}PROJECT_ROOT=${PROJECT_ROOT}${NC}"
echo -e "${YELLOW}PHASES=f0${START_PHASE_NUM}..f0${END_PHASE_NUM} (parallel tree vP1N)${NC}"

init_timing
cleanup_parallel_tree

if (( START_PHASE_NUM == 1 )); then
    if [[ -f ".mlops4ofp/setup.yaml" ]]; then
        echo -e "${YELLOW}Using existing setup (run-test2 never calls clean-setup).${NC}"
    else
        echo -e "${YELLOW}Setup not found; running non-destructive setup...${NC}"
        make setup SETUP_CFG=setup/local.yaml
    fi
else
    echo -e "${YELLOW}Skipping setup because start phase is f0${START_PHASE_NUM}.${NC}"
fi

if should_run_phase 1; then
    echo -e "${YELLOW}[TEST 1.0 -> v110]${NC}"
    timed_make f01 v110 variant1 VARIANT=v110 \
        RAW=data/raw.csv \
        CLEANING=basic \
        NAN_VALUES='[-999999]'
    timed_make f01 v110 script1 VARIANT=v110
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 1.1 -> v111]${NC}"
    timed_make f01 v111 variant1 VARIANT=v111 \
        RAW=data/raw.csv \
        CLEANING=basic \
        NAN_VALUES='[-999999]' \
        FIRST_LINE=1 MAX_LINES=50000
    timed_make f01 v111 script1 VARIANT=v111
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 2; then
    echo -e "${YELLOW}[TEST 2.0 -> v210]${NC}"
    timed_make f02 v210 variant2 VARIANT=v210 \
        PARENT=v110 \
        BANDS="[40, 60, 80]" \
        STRATEGY=transitions \
        NAN_MODE=keep
    timed_make f02 v210 script2 VARIANT=v210
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 2.1 -> v211]${NC}"
    timed_make f02 v211 variant2 VARIANT=v211 \
        PARENT=v110 \
        BANDS="[10, 20, 40, 60, 80, 90]" \
        STRATEGY=transitions \
        NAN_MODE=keep
    timed_make f02 v211 script2 VARIANT=v211
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 3; then
    echo -e "${YELLOW}[TEST 3.0 -> v310]${NC}"
    timed_make f03 v310 variant3 VARIANT=v310 \
        PARENT=v210 OW=6 LT=1 PW=1 \
        STRATEGY=synchro NAN_MODE=discard
    timed_make f03 v310 script3 VARIANT=v310
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 3.1 -> v311]${NC}"
    timed_make f03 v311 variant3 VARIANT=v311 \
        PARENT=v210 OW=6 LT=1 PW=1 \
        STRATEGY=asynOW NAN_MODE=discard
    timed_make f03 v311 script3 VARIANT=v311
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 3.2 -> v312]${NC}"
    timed_make f03 v312 variant3 VARIANT=v312 \
        PARENT=v211 OW=6 LT=1 PW=1 \
        STRATEGY=asynOW NAN_MODE=discard
    timed_make f03 v312 script3 VARIANT=v312
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 4; then
    echo -e "${YELLOW}[TEST 4.0 -> v410]${NC}"
    timed_make f04 v410 variant4 VARIANT=v410 \
        NAME=Battery_Active_Power_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["Battery_Active_Power_0_40-to-80_100","Battery_Active_Power_40_60-to-80_100","Battery_Active_Power_60_80-to-80_100"]'
    timed_make f04 v410 script4 VARIANT=v410
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.1 -> v411]${NC}"
    timed_make f04 v411 variant4 VARIANT=v411 \
        NAME=Battery_Active_Power_Set_Response_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["Battery_Active_Power_Set_Response_0_40-to-80_100","Battery_Active_Power_Set_Response_40_60-to-80_100","Battery_Active_Power_Set_Response_60_80-to-80_100"]'
    timed_make f04 v411 script4 VARIANT=v411
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.2 -> v412]${NC}"
    timed_make f04 v412 variant4 VARIANT=v412 \
        NAME=PVPCS_Active_Power_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["PVPCS_Active_Power_0_40-to-80_100","PVPCS_Active_Power_40_60-to-80_100","PVPCS_Active_Power_60_80-to-80_100"]'
    timed_make f04 v412 script4 VARIANT=v412
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.3 -> v413]${NC}"
    timed_make f04 v413 variant4 VARIANT=v413 \
        NAME=GE_Active_Power_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["GE_Active_Power_0_40-to-80_100","GE_Active_Power_40_60-to-80_100","GE_Active_Power_60_80-to-80_100"]'
    timed_make f04 v413 script4 VARIANT=v413
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.4 -> v414]${NC}"
    timed_make f04 v414 variant4 VARIANT=v414 \
        NAME=GE_Body_Active_Power_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["GE_Body_Active_Power_0_40-to-80_100","GE_Body_Active_Power_40_60-to-80_100","GE_Body_Active_Power_60_80-to-80_100"]'
    timed_make f04 v414 script4 VARIANT=v414
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.5 -> v415]${NC}"
    timed_make f04 v415 variant4 VARIANT=v415 \
        NAME=GE_Body_Active_Power_Set_Response_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["GE_Body_Active_Power_Set_Response_0_40-to-80_100","GE_Body_Active_Power_Set_Response_40_60-to-80_100","GE_Body_Active_Power_Set_Response_60_80-to-80_100"]'
    timed_make f04 v415 script4 VARIANT=v415
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.6 -> v416]${NC}"
    timed_make f04 v416 variant4 VARIANT=v416 \
        NAME=FC_Active_Power_FC_END_Set_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["FC_Active_Power_FC_END_Set_0_40-to-80_100","FC_Active_Power_FC_END_Set_40_60-to-80_100","FC_Active_Power_FC_END_Set_60_80-to-80_100"]'
    timed_make f04 v416 script4 VARIANT=v416
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.7 -> v417]${NC}"
    timed_make f04 v417 variant4 VARIANT=v417 \
        NAME=FC_Active_Power_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["FC_Active_Power_0_40-to-80_100","FC_Active_Power_40_60-to-80_100","FC_Active_Power_60_80-to-80_100"]'
    timed_make f04 v417 script4 VARIANT=v417
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 4.8 -> v418]${NC}"
    timed_make f04 v418 variant4 VARIANT=v418 \
        NAME=MG-LV-MSB_AC_Voltage_any-to-80_100 \
        PARENT=v310 OPERATOR=OR \
        EVENTS='["MG-LV-MSB_AC_Voltage_0_40-to-80_100","MG-LV-MSB_AC_Voltage_40_60-to-80_100","MG-LV-MSB_AC_Voltage_60_80-to-80_100"]'
    timed_make f04 v418 script4 VARIANT=v418
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 5; then
    echo -e "${YELLOW}[TEST 5.0 -> v510]${NC}"
    timed_make f05 v510 variant5 VARIANT=v510 PARENT=v410 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v510 script5 VARIANT=v510
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.1 -> v511]${NC}"
    timed_make f05 v511 variant5 VARIANT=v511 PARENT=v411 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v511 script5 VARIANT=v511
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.2 -> v512]${NC}"
    timed_make f05 v512 variant5 VARIANT=v512 PARENT=v412 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v512 script5 VARIANT=v512
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.3 -> v513]${NC}"
    timed_make f05 v513 variant5 VARIANT=v513 PARENT=v413 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v513 script5 VARIANT=v513
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.4 -> v514]${NC}"
    timed_make f05 v514 variant5 VARIANT=v514 PARENT=v414 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v514 script5 VARIANT=v514
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.5 -> v515]${NC}"
    timed_make f05 v515 variant5 VARIANT=v515 PARENT=v415 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v515 script5 VARIANT=v515
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.6 -> v516]${NC}"
    timed_make f05 v516 variant5 VARIANT=v516 PARENT=v416 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v516 script5 VARIANT=v516
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.7 -> v517]${NC}"
    timed_make f05 v517 variant5 VARIANT=v517 PARENT=v417 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v517 script5 VARIANT=v517
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 5.8 -> v518]${NC}"
    timed_make f05 v518 variant5 VARIANT=v518 PARENT=v418 \
        MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
    timed_make f05 v518 script5 VARIANT=v518
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 6; then
    echo -e "${YELLOW}[TEST 6.0 -> v610]${NC}"
    timed_make f06 v610 variant6 VARIANT=v610 PARENT=v510
    timed_make f06 v610 script6 VARIANT=v610
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.1 -> v611]${NC}"
    timed_make f06 v611 variant6 VARIANT=v611 PARENT=v511
    timed_make f06 v611 script6 VARIANT=v611
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.2 -> v612]${NC}"
    timed_make f06 v612 variant6 VARIANT=v612 PARENT=v512
    timed_make f06 v612 script6 VARIANT=v612
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.3 -> v613]${NC}"
    timed_make f06 v613 variant6 VARIANT=v613 PARENT=v513
    timed_make f06 v613 script6 VARIANT=v613
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.4 -> v614]${NC}"
    timed_make f06 v614 variant6 VARIANT=v614 PARENT=v514
    timed_make f06 v614 script6 VARIANT=v614
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.5 -> v615]${NC}"
    timed_make f06 v615 variant6 VARIANT=v615 PARENT=v515
    timed_make f06 v615 script6 VARIANT=v615
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.6 -> v616]${NC}"
    timed_make f06 v616 variant6 VARIANT=v616 PARENT=v516
    timed_make f06 v616 script6 VARIANT=v616
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.7 -> v617]${NC}"
    timed_make f06 v617 variant6 VARIANT=v617 PARENT=v517
    timed_make f06 v617 script6 VARIANT=v617
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 6.8 -> v618]${NC}"
    timed_make f06 v618 variant6 VARIANT=v618 PARENT=v518
    timed_make f06 v618 script6 VARIANT=v618
    echo -e "${GREEN}[✓] PASSED${NC}"
    echo ""
fi

if should_run_phase 7; then
    for i in "${!PHASE7_VARIANTS[@]}"; do
        echo -e "${YELLOW}[TEST 7.${i} -> ${PHASE7_VARIANTS[$i]}]${NC}"
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

if should_run_phase 8; then
    echo -e "${YELLOW}[TEST 8.0 - manual baseline -> v810]${NC}"
    timed_make f08 v810 variant8 VARIANT=v810 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01
    timed_make f08 v810 script8 VARIANT=v810
    echo -e "${GREEN}[✓] PASSED v810${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 8.1 - auto_ilp max_global_recall -> v811]${NC}"
    timed_make f08 v811 variant8 VARIANT=v811 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_global_recall
    timed_make f08 v811 script8 VARIANT=v811
    echo -e "${GREEN}[✓] PASSED v811${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 8.2 - auto_ilp max_tp -> v812]${NC}"
    timed_make f08 v812 variant8 VARIANT=v812 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_tp
    timed_make f08 v812 script8 VARIANT=v812
    echo -e "${GREEN}[✓] PASSED v812${NC}"
    echo ""

    echo -e "${YELLOW}[TEST 8.3 - auto_ilp max_tp + filters -> v813]${NC}"
    timed_make f08 v813 variant8 VARIANT=v813 \
        PARENTS="${PHASE8_PARENT_VARIANTS}" \
        PLATFORM=esp32 MTI_MS=100 TIME_SCALE=0.01 \
        SELECTION_MODE=auto_ilp OBJECTIVE=max_tp \
        MIN_PRECISION=0.01 MIN_RECALL=0.05
    timed_make f08 v813 script8 VARIANT=v813
    echo -e "${GREEN}[✓] PASSED v813${NC}"
    echo ""
fi

echo -e "${GREEN}Run completed from f0${START_PHASE_NUM} to f0${END_PHASE_NUM} for parallel tree vP1N.${NC}"
echo -e "${GREEN}[TIMING] Results in ${TIMING_CSV}${NC}"