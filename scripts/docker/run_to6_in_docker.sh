#!/usr/bin/env bash
set -euo pipefail

# Ejecuta test/run-test.sh --to 6 dentro de un contenedor Linux reproducible
# y exporta resultados a scripts/docker-artifacts/executions-<host_tag>.
#
# Uso:
#   bash scripts/docker/run_to6_in_docker.sh macos
#   bash scripts/docker/run_to6_in_docker.sh windows
#   bash scripts/docker/run_to6_in_docker.sh linux

if [[ $# -lt 1 ]]; then
  echo "Uso: $0 <host_tag>"
  exit 1
fi

HOST_TAG="$1"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ARTIFACTS_DIR="${ROOT_DIR}/scripts/docker-artifacts"
IMAGE_NAME="mlops4ofp-run-to6:py311"

mkdir -p "${ARTIFACTS_DIR}"

echo "[INFO] Building image ${IMAGE_NAME}"
docker build \
  -f "${ROOT_DIR}/scripts/docker/Dockerfile.run-to6" \
  -t "${IMAGE_NAME}" \
  "${ROOT_DIR}"

echo "[INFO] Running run-test --to 6 in container for host_tag=${HOST_TAG}"
docker run --rm \
  -v "${ROOT_DIR}:/workspace:ro" \
  -v "${ARTIFACTS_DIR}:/artifacts" \
  "${IMAGE_NAME}" \
  bash -lc "
    set -euo pipefail
    rm -rf /tmp/mlops && mkdir -p /tmp/mlops
    cp -a /workspace/. /tmp/mlops/
    cd /tmp/mlops
    bash test/run-test.sh --to 6
    rm -rf /artifacts/executions-${HOST_TAG} /artifacts/timing-${HOST_TAG}
    cp -a executions /artifacts/executions-${HOST_TAG}
    cp -a test/timing /artifacts/timing-${HOST_TAG}
  "

echo "[OK] Saved executions in ${ARTIFACTS_DIR}/executions-${HOST_TAG}"
echo "[OK] Saved timing in ${ARTIFACTS_DIR}/timing-${HOST_TAG}"
