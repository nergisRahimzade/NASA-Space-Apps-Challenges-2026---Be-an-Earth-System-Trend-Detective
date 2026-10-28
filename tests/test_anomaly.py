import numpy as np
import pandas as pd
import pytest

from src.anomaly import calculate_anomaly, calculate_climatology


@pytest.fixture
def fake_climate_data():
    dates = pd.date_range(start="2020-01-01", periods=24, freq="ME")
    
    # Create a predictable pattern: repeating 10 for Jan, 20 for Feb...
    base_pattern = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0, 120.0]
    values = base_pattern * 2  # 24 months total
    
    return pd.Series(values, index=dates)

def test_climatology_averages(fake_climate_data):
    climatology = calculate_climatology(fake_climate_data)
    
    assert len(climatology) == 12
    assert climatology[1] == 10.0   # January average
    assert climatology[12] == 120.0 # December average

def test_anomaly_removes_seasonality(fake_climate_data):
    climatology = calculate_climatology(fake_climate_data)
    anomalies = calculate_anomaly(fake_climate_data, climatology)
    
    # anomalies should be exactly 0
    np.testing.assert_array_almost_equal(anomalies.values, np.zeros(24))

