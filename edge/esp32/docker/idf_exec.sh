#!/usr/bin/env bash

# ============================================================
# idf_exec.sh
# Wrapper reproducible para ejecutar idf.py dentro de Docker
# ============================================================

set -e

IMAGE_NAME="mlops4ofp-idf:6.0"

# ------------------------------------------
# Resolver rutas
# ------------------------------------------

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
EDGE_DIR="$( dirname "$SCRIPT_DIR" )"
PROJECT_DIR="${EDGE_DIR}/template_project"

if [ ! -d "$PROJECT_DIR" ]; then
  echo "[ERROR] template_project not found at:"
  echo "        $PROJECT_DIR"
  exit 1
fi

if [ -z "$F07_VARIANT_DIR" ]; then
  echo "[ERROR] F07_VARIANT_DIR environment variable not set."
  echo "Example:"
  echo "  export F07_VARIANT_DIR=executions/f07modval/v701"
  exit 1
fi

VARIANT_DIR_ABS="$(cd "$F07_VARIANT_DIR" && pwd)"

GENERATED_DIR="${VARIANT_DIR_ABS}/build_generated"
DATA_DIR="${VARIANT_DIR_ABS}/data"

if [ ! -d "$GENERATED_DIR" ]; then
  echo "[ERROR] generated_sources not found at:"
  echo "        $GENERATED_DIR"
  exit 1
fi

if [ ! -d "$DATA_DIR" ]; then
  echo "[ERROR] data directory not found at:"
  echo "        $DATA_DIR"
  exit 1
fi

if [ "$#" -eq 0 ]; then
  echo "[ERROR] No idf.py command provided."
  echo "Usage:"
  echo "  ./idf_exec.sh build"
  echo "  ./idf_exec.sh flash"
  echo "  ./idf_exec.sh monitor"
  exit 1
fi

echo "==============================================="
echo " ESP32 Docker Execution"
echo " Image:     $IMAGE_NAME"
echo " Project:   $PROJECT_DIR"
echo " Variant:   $VARIANT_DIR_ABS"
echo " Command:   idf.py $@"
echo "==============================================="

docker run --rm -it \
  --platform linux/amd64 \
  -v "$PROJECT_DIR":/project \
  -v "$GENERATED_DIR":/project/build/build_generated \
  -v "$DATA_DIR":/project/data \
  -w /project \
  --entrypoint /bin/bash \
  $IMAGE_NAME \
  -c "source /opt/esp/idf/export.sh && idf.py $@"
  