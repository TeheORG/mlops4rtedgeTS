#!/usr/bin/env bash

# ============================================================
# Build Docker image for ESP-IDF runtime (IDF 6.0)
# ============================================================

set -e

IMAGE_NAME="mlops4ofp-idf"
IMAGE_TAG="6.0"
DOCKER_PLATFORM="${DOCKER_PLATFORM:-linux/amd64}"

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "==============================================="
echo " Building Docker image for ESP32 runtime"
echo " Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo " Platform: ${DOCKER_PLATFORM}"
echo " Dockerfile: ${SCRIPT_DIR}/Dockerfile"
echo "==============================================="

docker build \
  --platform "${DOCKER_PLATFORM}" \
  -t ${IMAGE_NAME}:${IMAGE_TAG} \
  -f "${SCRIPT_DIR}/Dockerfile" \
  "${SCRIPT_DIR}"
  
echo
echo "==============================================="
echo " Docker image built successfully:"
echo "   ${IMAGE_NAME}:${IMAGE_TAG}"
echo "==============================================="
