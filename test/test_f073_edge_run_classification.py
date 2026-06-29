import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.phases.f073_post import classify_edge_run


def test_completed_run():
    result = classify_edge_run(
        {
            "n_attempts": 6144,
            "n_ok": 6144,
            "n_fail": 0,
            "ok_rate": 1.0,
            "fail_rate": 0.0,
            "wd_late_rate": 0.0,
            "wd_early_rate": 0.0,
            "infer_mean_ms": 3.237,
            "infer_max_ms": 6.0,
            "itmax_ms": 100.0,
        }
    )
    assert result["phase_status_reason"] == "completed"
    assert result["edge_run_completed"] is True


def test_low_ok_rate_run():
    result = classify_edge_run(
        {
            "n_attempts": 9662,
            "n_ok": 864,
            "n_fail": 8798,
            "n_urgent": 8798,
            "ok_rate": 0.0894,
            "fail_rate": 0.9106,
            "wd_late_rate": 0.9106,
            "wd_early_rate": 0.0,
            "infer_mean_ms": 452913.08,
            "itmax_ms": 100.0,
        }
    )
    assert result["phase_status_reason"] == "low_ok_rate"
    assert result["edge_run_completed"] is False
    assert result["validation"]["dominant_failure_kind"] == "urgent_fallback"
    assert "review_time_scale_factor_MTI_MS_ITmax_and_serial_period" in result["validation"]["likely_causes"]


def test_monitor_missing():
    result = classify_edge_run({}, monitor_present=False)
    assert result["phase_status_reason"] == "monitor_missing"
    assert result["edge_run_completed"] is False


def test_serial_open_failed():
    result = classify_edge_run({}, serial_open_failed=True)
    assert result["phase_status_reason"] == "serial_open_failed"
    assert result["edge_run_completed"] is False


if __name__ == "__main__":
    test_completed_run()
    test_low_ok_rate_run()
    test_monitor_missing()
    test_serial_open_failed()
