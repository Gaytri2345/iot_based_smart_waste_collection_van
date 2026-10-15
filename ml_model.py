"""
Time-to-full prediction with Scikit-learn LinearRegression.

Data     : historical (timestamp, fill_percentage) rows from bin_readings, one bin at a time.
Features : X = hours elapsed since the start of the current fill cycle.
Target   : y = fill percentage.
Model    : y = slope * t + intercept  (slope = fill rate in % per hour).
Output   : estimated hours until fill reaches FULL_THRESHOLD, and fill expected after 1 hour.
Estimate only - real filling is irregular, so this is approximate, never exact.
"""
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
import config


def _current_cycle(s: pd.Series) -> pd.Series:
    """Drop data from before the bin was last emptied (a big sudden fall in fill %)."""
    drops = s.diff() <= -config.EMPTIED_DROP
    if drops.any():
        s = s[s.index >= drops[drops].index[-1]]
    return s


def predict_bin(df: pd.DataFrame, horizon_h: float = 1.0) -> dict:
    out = {"current_fill": None, "predicted_fill": None, "hours_to_full": None,
           "rate_per_hour": None, "r2": None, "note": ""}
    if df is None or df.empty:
        out["note"] = "No readings yet."
        return out

    d = df.sort_values("timestamp").set_index("timestamp")["fill_percentage"].astype(float)
    current = float(d.iloc[-1])
    out["current_fill"] = current

    if current >= config.FULL_THRESHOLD:
        out["hours_to_full"] = 0.0
        out["predicted_fill"] = min(100.0, current)
        out["note"] = "Already at/above the full threshold."
        return out

    s = _current_cycle(d.resample(config.RESAMPLE).mean().dropna())
    span_min = (s.index[-1] - s.index[0]).total_seconds() / 60 if len(s) > 1 else 0
    if len(s) < config.MIN_POINTS or span_min < config.MIN_SPAN_MIN:
        out["note"] = "Not enough history in the current fill cycle yet."
        return out

    t = ((s.index - s.index[0]).total_seconds() / 3600.0).to_numpy().reshape(-1, 1)
    model = LinearRegression().fit(t, s.to_numpy())
    slope = float(model.coef_[0])
    out["rate_per_hour"] = slope
    out["r2"] = float(model.score(t, s.to_numpy()))

    out["predicted_fill"] = float(np.clip(current + slope * horizon_h, 0, 100))
    if slope < config.MIN_SLOPE:
        out["note"] = "Bin is not filling noticeably."
        return out
    out["hours_to_full"] = (config.FULL_THRESHOLD - current) / slope
    out["note"] = "Estimate from linear fill-rate trend."
    return out


def fmt_hours(h):
    if h is None:
        return "Unknown"
    if h <= 0:
        return "Full now"
    if h < 1:
        return f"~{int(round(h * 60))} min"
    return f"~{h:.1f} hours"
