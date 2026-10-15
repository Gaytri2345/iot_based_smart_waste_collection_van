"""
Creates SIMULATED history (flagged is_simulated = true) so the ML has data on demo day.
Usage:  python seed_demo_data.py            (48 h of history)
        python seed_demo_data.py --clear    (delete simulated rows only)
Needs env vars SUPABASE_URL and SUPABASE_SERVICE_KEY.
"""
import os, sys
from datetime import datetime, timedelta, timezone
import numpy as np
from supabase import create_client
import config

sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

if "--clear" in sys.argv:
    sb.table("bin_readings").delete().eq("is_simulated", True).execute()
    print("Simulated rows deleted.")
    sys.exit()

rng = np.random.default_rng(42)
HOURS, STEP_MIN = 48, 5
# fill rate in % per hour and the fill level the bin should have at "now"
PROFILE = {"B01": dict(rate=4.0, now_fill=65.0), "B02": dict(rate=2.0, now_fill=42.0)}

def status(f):
    return "FULL" if f >= config.FULL_THRESHOLD else "MEDIUM" if f >= config.MEDIUM_THRESHOLD else "NORMAL"

now = datetime.now(timezone.utc)
n = HOURS * 60 // STEP_MIN
for bin_id, p in PROFILE.items():
    # walk backwards from "now" so the last value matches now_fill; wrap around when bin was emptied
    fills, f = [], p["now_fill"]
    for i in range(n):
        fills.append(f)
        f -= p["rate"] * STEP_MIN / 60 * rng.uniform(0.6, 1.4)
        if f < 3:                       # going back in time: previous cycle ended full
            f = rng.uniform(88, 96)
    fills.reverse()
    rows = []
    for i, f in enumerate(fills):
        f = float(np.clip(f + rng.normal(0, 0.8), 0, 100))
        ts = now - timedelta(minutes=STEP_MIN * (n - 1 - i))
        dist = config.MIN_DISTANCE_CM + (1 - f / 100) * (config.BIN1_DEPTH_CM - config.MIN_DISTANCE_CM)
        rows.append(dict(bin_id=bin_id, distance_cm=round(dist, 1), fill_percentage=round(f, 1),
                         status=status(f), collection_required=f >= config.FULL_THRESHOLD,
                         timestamp=ts.isoformat(), is_simulated=True))
    for i in range(0, len(rows), 200):
        sb.table("bin_readings").insert(rows[i:i + 200]).execute()
    print(f"{bin_id}: inserted {len(rows)} simulated readings")
