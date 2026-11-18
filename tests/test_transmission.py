import pandas as pd
import pytest

from myquant.studies.transmission import lead_lag_panel


def test_lead_lag_panel_uses_only_prior_source_values():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=4, freq="D", tz="UTC"),
        "source_value": [10.0, 20.0, 30.0, 40.0],
        "target_return": [0.0, 0.1, 0.2, 0.3],
    })
    result = lead_lag_panel(frame, source_lags=(1,))
    assert pd.isna(result.loc[0, "source_lag_1"])
    assert result.loc[1, "source_lag_1"] == 10.0


def test_lead_lag_panel_rejects_duplicate_timestamps():
    frame = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-01-01", "2026-01-01"], utc=True),
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    with pytest.raises(ValueError, match="unique"):
        lead_lag_panel(frame, source_lags=(1,))


def test_lead_lag_panel_rejects_contemporaneous_zero_lag():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    with pytest.raises(ValueError, match="positive"):
        lead_lag_panel(frame, source_lags=(0,))


def test_lead_lag_panel_supports_custom_timestamp_column():
    frame = pd.DataFrame({
        "observed_at": pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    result = lead_lag_panel(frame, source_lags=(1,), timestamp_column="observed_at")
    assert result.loc[1, "source_lag_1"] == 1.0


def test_lead_lag_panel_rejects_string_timestamps():
    frame = pd.DataFrame({
        "timestamp": ["2026-01-01", "2026-01-02"],
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    with pytest.raises(TypeError, match="datetime"):
        lead_lag_panel(frame, source_lags=(1,))


def test_lead_lag_panel_rejects_naive_timestamps():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=2, freq="D"),
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    with pytest.raises(ValueError, match="timezone-aware"):
        lead_lag_panel(frame, source_lags=(1,))


def test_lead_lag_panel_rejects_non_integer_lags():
    frame = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=2, freq="D", tz="UTC"),
        "source_value": [1.0, 2.0],
        "target_return": [0.0, 0.1],
    })
    with pytest.raises(TypeError, match="integers"):
        lead_lag_panel(frame, source_lags=(True,))
    with pytest.raises(TypeError, match="integers"):
        lead_lag_panel(frame, source_lags=(1.5,))
