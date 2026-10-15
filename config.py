"""Shared settings for dashboard, ML and seed script. Keep thresholds equal to the ESP32 code."""

# Fill thresholds (%)
MEDIUM_THRESHOLD = 50
FULL_THRESHOLD = 80

# Bin geometry (cm) - same as ESP32 firmware (used only by the seed script)
BIN1_DEPTH_CM = 11
BIN2_DEPTH_CM = 12
MIN_DISTANCE_CM = 3.0

# Van start point (depot). CHANGE to your real depot / parking location.
DEPOT = {
    "name": "Van Depot",
    "latitude": 19.98659,
    "longitude": 73.78276
}
# Dashboard
DASHBOARD_REFRESH_SEC = 15
OFFLINE_AFTER_SEC = 120        # warn if no new reading for this long

# ML
ML_WINDOW_HOURS = 12           # how much history the model looks at
RESAMPLE = "2min"              # readings are averaged into this time step
MIN_POINTS = 5                 # minimum resampled points needed to fit
MIN_SPAN_MIN = 10              # minimum minutes of data in the current fill cycle
EMPTIED_DROP = 30              # a fall of >= 30 % between steps = bin was emptied
MIN_SLOPE = 0.05               # % per hour; below this the bin is "not filling"
