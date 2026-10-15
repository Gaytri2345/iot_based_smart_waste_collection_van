"""Driver dashboard backend (Flask) - IoT-Based Smart Waste Collection Van.
Run:  python app.py   then open http://localhost:5000
The page itself is plain HTML/CSS/JS in /static; this file only serves one JSON endpoint.
"""
import os
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from supabase import create_client

import config
from ml_model import predict_bin, fmt_hours
from route_planner import plan_route

load_dotenv()
app = Flask(__name__, static_folder="static", static_url_path="/static")
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])
_last_saved = {}  # bin_id -> unix time of last stored prediction


def fetch_history(bin_id, hours=config.ML_WINDOW_HOURS):
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows, start = [], 0
    while True:  # Supabase returns max 1000 rows per request -> page through
        r = (sb.table("bin_readings")
               .select("timestamp,distance_cm,fill_percentage,status,collection_required")
               .eq("bin_id", bin_id).gte("timestamp", since).order("timestamp")
               .range(start, start + 999).execute().data)
        rows += r
        if len(r) < 1000:
            break
        start += 1000
    df = pd.DataFrame(rows)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def save_prediction(bin_id, pred):
    """Store a prediction at most once every 5 minutes per bin."""
    if time.time() - _last_saved.get(bin_id, 0) < 300 or pred["current_fill"] is None:
        return
    sb.table("predictions").insert({
        "bin_id": bin_id,
        "current_fill": round(pred["current_fill"], 1),
        "predicted_fill": None if pred["predicted_fill"] is None else round(pred["predicted_fill"], 1),
        "predicted_time_to_full": None if pred["hours_to_full"] is None else round(pred["hours_to_full"], 2),
    }).execute()
    _last_saved[bin_id] = time.time()


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/dashboard")
def dashboard():
    now = datetime.now(timezone.utc)
    bins_out, need = [], []

    for b in sb.table("bins").select("*").order("bin_id").execute().data:
        df = fetch_history(b["bin_id"])
        pred = predict_bin(df)
        save_prediction(b["bin_id"], pred)
        item = {"bin_id": b["bin_id"], "bin_name": b["bin_name"],
                "latitude": b["latitude"], "longitude": b["longitude"],
                "has_data": not df.empty, "note": pred["note"],
                "rate_per_hour": pred["rate_per_hour"],
                "eta_text": fmt_hours(pred["hours_to_full"]),
                "history": []}
        if not df.empty:
            last = df.iloc[-1]
            age = int((now - last["timestamp"]).total_seconds())
            item.update(fill=round(float(last["fill_percentage"]), 1), status=last["status"],
                        distance_cm=float(last["distance_cm"]), age_sec=age,
                        offline=age > config.OFFLINE_AFTER_SEC,
                        collection_required=bool(last["collection_required"]))
            h = df.set_index("timestamp")["fill_percentage"].resample("5min").mean().dropna()
            item["history"] = [{"t": t.isoformat(), "v": round(float(v), 1)} for t, v in h.items()]
            if item["collection_required"]:
                need.append(b | {"bin_id": b["bin_id"], "fill": item["fill"]})
        bins_out.append(item)
    
    route, km = plan_route(config.DEPOT, need)
    
    

    # leg distances for a simple step-by-step list (straight-line, approximate)
    from route_planner import haversine_km
    
    steps, prev = [], config.DEPOT

    for r in route:
        steps.append({
            "bin_id": r["bin_id"],
            "bin_name": r["bin_name"],
            "fill": r["fill"],
            "leg_km": round(haversine_km(prev, r), 2)
        })
        prev = r

    if route:
        steps.append({
            "bin_id": "DEPOT",
            "bin_name": "Van Depot (Return)",
            "fill": 0,
            "leg_km": round(haversine_km(prev, config.DEPOT), 2)
        })

    
    return jsonify({
        "server_time": now.isoformat(),
        "refresh_sec": config.DASHBOARD_REFRESH_SEC,
        "thresholds": {
            "medium": config.MEDIUM_THRESHOLD,
            "full": config.FULL_THRESHOLD
        },
        "depot": config.DEPOT["name"],
        "bins": bins_out,
        "route": {
            "steps": steps,
            "total_km": round(km, 2)
        },
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
