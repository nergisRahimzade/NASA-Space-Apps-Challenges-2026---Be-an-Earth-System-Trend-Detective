import pandas as pd


def calculate_climatology(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("Series index must be a DatetimeIndex.")
        
    return series.groupby(series.index.month).mean()

def calculate_anomaly(series: pd.Series, climatology: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("Series index must be a DatetimeIndex.")
        
    return series - series.index.month.map(climatology)

