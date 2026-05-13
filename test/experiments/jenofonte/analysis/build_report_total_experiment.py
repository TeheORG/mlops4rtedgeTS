#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    target_script = repo_root / "analysis" / "build_report_total_experiment.py"
    if not target_script.exists():
        raise FileNotFoundError(f"Target script not found: {target_script}")
    runpy.run_path(str(target_script), run_name="__main__")


if __name__ == "__main__":
    main()
