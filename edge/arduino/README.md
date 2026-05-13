# Arduino Edge Backend

This folder defines the Arduino edge backend scaffold for F07.

Expected structure:
- `template_project/`: board/runtime template copied by `f071_preparebuild.py`.

Notes:
- Code generation contracts (config.h, models_data.c, input_dataset.csv) should match the ESP32 backend.
- Runtime adapters for flash/run are not implemented yet in `f072_flashrun.py`.
