# F07 STM32 Runner

Scripts consumed by `scripts/phases/f072_flashrun.py` when `platform=stm32`.

Required scripts:
- `build.sh`
- `flash.sh`
- `run.sh`

Inputs provided through environment variables:
- `F07_PROJECT_DIR`
- `F07_VARIANT_DIR`
- `F07_EDGE_CONFIG`
- `F07_INPUT_DATASET`
- `F07_PORT` (if set)
- `F07_BAUD`
- `F07_MODE`
- `F07_TU_MS`
- `F07_RECOMMENDED_DRAIN_SECONDS`
- `F07_DRAIN_SECONDS` (if set)
