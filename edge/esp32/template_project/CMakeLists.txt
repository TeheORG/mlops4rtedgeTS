cmake_minimum_required(VERSION 3.16)

# ============================================================
# ESP-IDF Project Configuration
# ============================================================

# Ruta opcional a artefactos generados por F07
set(GENERATED_DIR "${CMAKE_SOURCE_DIR}/build_generated")

# Si existe build_generated, lo añadimos al include path
if(EXISTS ${GENERATED_DIR})
    message(STATUS "Using build_generated directory: ${GENERATED_DIR}")
    include_directories(${GENERATED_DIR})
else()
    message(WARNING "build_generated directory not found. Building without variant artifacts.")
endif()

include($ENV{IDF_PATH}/tools/cmake/project.cmake)

project(MLOps4OFP)