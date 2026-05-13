#!/bin/bash
set -o pipefail

LOGFILE="$(dirname "$0")/run-test-audit.log"

TRACEFILE="$(dirname "$0")/run-test-audit-trace.log"
exec > >(tee "$LOGFILE") 2>&1

log_trace() {
  # Registra sólo órdenes make completas y su resultado
  local status="$1"; shift
  local cmd="$*"
  local now
  now=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$now | $status | $cmd" >> "$TRACEFILE"
}

log_error_trace() {
  local msg="$1"
  local now
  now=$(date '+%Y-%m-%d %H:%M:%S')
  echo "$now | ERROR | $msg" >> "$TRACEFILE"
}
TMPERR=$(mktemp)
EXITCODE=0

log_ok()   { echo "[OK]   $1"; }
log_fail() { echo "[FAIL] $1"; cat "$TMPERR"; EXITCODE=1; }

run_expect_ok() {
  "$@" >"$TMPERR" 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then
    log_ok "$*"
    log_trace OK "$*"
  else
    log_fail "$*"
    log_error_trace "FAILED: $* | $(head -1 "$TMPERR")"
  fi
}

run_expect_fail() {
  "$@" >"$TMPERR" 2>&1
  local rc=$?
  if [ $rc -eq 0 ]; then
    log_ok "$* (expected FAIL)"
    log_trace OK "$* (expected FAIL)"
  else
    log_ok "$* (correctly failed)"
    log_trace FAIL "$* (correctly failed)"
    log_error_trace "EXPECTED FAIL: $* | $(head -1 "$TMPERR")"
  fi
}

echo "========================================"
echo " EXPERIMENT: AUDITABILITY DEMONSTRATION "
echo "========================================"

############################################
# CLEAN
############################################

echo "[STEP 0] Cleaning all variants"
for p in {1..8}; do make remove${p}-all >/dev/null 2>&1 || true; done

############################################
# STEP 1 — CREATION OK CHAIN
############################################

echo "[STEP 1] Creating valid chain v105 -> v205 -> v305"

run_expect_ok make variant1 VARIANT=v105 RAW=data/raw.csv CLEANING=basic NAN_VALUES='[-999999]' MAX_LINES=2000
run_expect_ok make script1 VARIANT=v105
run_expect_ok make register1 VARIANT=v105
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register1"; fi

run_expect_ok make variant2 VARIANT=v205 PARENT=v105 BANDS="[40, 60, 80]" STRATEGY=transitions NAN_MODE=keep
run_expect_ok make script2 VARIANT=v205
run_expect_ok make register2 VARIANT=v205
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register2"; fi

run_expect_ok make variant3 VARIANT=v305 PARENT=v205 OW=6 LT=1 PW=1 STRATEGY=synchro NAN_MODE=discard
run_expect_ok make script3 VARIANT=v305
run_expect_ok make register3 VARIANT=v305
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register3"; fi

############################################
# STEP 2 — MISSING PARENT
############################################

echo "[STEP 2] Creating v505 WITHOUT v405 (must fail)"
set +e
run_expect_fail make variant5 VARIANT=v505 PARENT=v405 MODEL_FAMILY=dense_bow IMBALANCE_STRATEGY=none
set +e
rm -rf executions/f05_modeling/v505 2>/dev/null || true

echo "[STEP 2b] Creating missing parent v405"

run_expect_ok make variant4 VARIANT=v405 NAME=Battery_Active_Power_any-to-80_100 PARENT=v305 OPERATOR=OR EVENTS='["FC_Active_Power_0_40-to-80_100","FC_Active_Power_40_60-to-80_100","FC_Active_Power_60_80-to-80_100"]'
run_expect_ok make script4 VARIANT=v405
run_expect_ok make register4 VARIANT=v405
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register4"; fi

echo "[STEP 2c] Now v505 should work"

run_expect_ok make variant5 VARIANT=v505 PARENT=v405 MODEL_FAMILY=cnn1d IMBALANCE_STRATEGY=rare_events IMBALANCE_MAX_MAJ=20000
run_expect_ok make script5 VARIANT=v505
run_expect_ok make register5 VARIANT=v505
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register5"; fi

############################################
# STEP 3 — TAMPERING outputs.yaml
############################################

echo "[STEP 3] Modify parent outputs.yaml -> must break child register"

run_expect_ok make variant6 VARIANT=v605 PARENT=v505
run_expect_ok make script6 VARIANT=v606

PARENT_OUTPUTS="executions/f05_modeling/v505/outputs.yaml"
PARENT_OUTPUTS_BAK=$(mktemp)
cp "$PARENT_OUTPUTS" "$PARENT_OUTPUTS_BAK"

echo "[INFO] Tampering outputs.yaml of parent v505"
echo "# tamper $(date)" >> "$PARENT_OUTPUTS"

run_expect_fail make register6 VARIANT=v605

echo "[INFO] Reverting outputs.yaml"
cp "$PARENT_OUTPUTS_BAK" "$PARENT_OUTPUTS"
rm -f "$PARENT_OUTPUTS_BAK"

echo "[STEP 3b] Register should now work"

run_expect_ok make register6 VARIANT=v605
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register6-605"; fi

############################################
# STEP 4 — TAMPERING SOURCE CODE
############################################

echo "[STEP 4] Modify phase code -> must break register"

run_expect_ok make variant6 VARIANT=v606 PARENT=v505
run_expect_ok make script6 VARIANT=v606

echo "[INFO] Tampering source code (f06)"
echo "# tamper $(date)" >> scripts/phases/f06_packaging.py

run_expect_fail make register6 VARIANT=v606

echo "[INFO] Reverting source code"
git checkout -- scripts/phases/f06_packaging.py

echo "[STEP 4b] Register should now work"

run_expect_ok make register6 VARIANT=v606
if [ -n "$(git status --porcelain scripts/)" ]; then git add scripts/ && git commit -m "Auto-commit scripts/ before register6-606"; fi

############################################

echo "========================================"
echo " RESULT: AUDITABILITY TEST COMPLETED "
echo "========================================"

rm "$TMPERR"
exit $EXITCODE
