#!/usr/bin/env bash
set -euo pipefail

# Compara dos carpetas executions-<host> generadas por run_to6_in_docker.sh.
#
# Uso:
#   bash scripts/docker/compare_host_runs.sh macos linux
#   bash scripts/docker/compare_host_runs.sh windows linux

if [[ $# -lt 2 ]]; then
  echo "Uso: $0 <left_host_tag> <right_host_tag>"
  exit 1
fi

LEFT_TAG="$1"
RIGHT_TAG="$2"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACTS_DIR="${ROOT_DIR}/scripts/docker-artifacts"

LEFT_DIR="${ARTIFACTS_DIR}/executions-${LEFT_TAG}"
RIGHT_DIR="${ARTIFACTS_DIR}/executions-${RIGHT_TAG}"

if [[ ! -d "${LEFT_DIR}" ]]; then
  echo "[ERROR] Missing ${LEFT_DIR}"
  exit 1
fi

if [[ ! -d "${RIGHT_DIR}" ]]; then
  echo "[ERROR] Missing ${RIGHT_DIR}"
  exit 1
fi

OUT_CSV="${ARTIFACTS_DIR}/compare-${LEFT_TAG}-vs-${RIGHT_TAG}.csv"
OUT_MD="${ARTIFACTS_DIR}/compare-${LEFT_TAG}-vs-${RIGHT_TAG}.md"

echo "[INFO] Generating CSV comparison: ${OUT_CSV}"
python3 "${ROOT_DIR}/test/compare_execution_roots.py" \
  --left "${LEFT_DIR}" \
  --right "${RIGHT_DIR}" \
  --left-label "${LEFT_TAG}" \
  --right-label "${RIGHT_TAG}" \
  --output "${OUT_CSV}"

echo "[INFO] Generating Markdown comparison: ${OUT_MD}"
python3 "${ROOT_DIR}/test/compare_execution_roots.py" \
  --left "${LEFT_DIR}" \
  --right "${RIGHT_DIR}" \
  --left-label "${LEFT_TAG}" \
  --right-label "${RIGHT_TAG}" \
  --output "${OUT_MD}"

echo "[OK] Comparison done"
