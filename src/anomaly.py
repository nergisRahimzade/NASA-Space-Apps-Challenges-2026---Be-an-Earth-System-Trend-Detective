import pandas as pd

def calculate_climatology(series: pd.Series) -> pd.Series:
    """
    Input index must be a DatetimeIndex.
    Returns a Series of 12 values mapped to month numbers.
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Series index must be a DatetimeIndex.")
        
    return series.groupby(series.index.month).mean()

def calculate_anomaly(series: pd.Series, climatology: pd.Series) -> pd.Series:
    """
    Subtracts the historical monthly baseline from the raw time-series values.
    Returns a time-series of anomalies.
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("Series index must be a DatetimeIndex.")
        
    return series - series.index.month.map(climatology)

