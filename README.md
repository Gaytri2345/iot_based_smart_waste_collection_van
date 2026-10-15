# IoT-Based Smart Waste Collection Van

**Smart Bin → Ultrasonic Sensor → ESP32 → Wi-Fi → Supabase → ML Prediction → Full-Bin Detection → Route Generation → Driver Dashboard** (no map - route is shown as a step list)

Two fixed bins. Their latitude/longitude are stored **once** in the cloud `bins` table (no GPS module). The dashboard reads those coordinates, picks the bins that are actually full, and builds the route from the van depot.

## 1. Files

| File | Purpose |
|---|---|
| `supabase_schema.sql` | Creates `bins`, `bin_readings`, `predictions`, inserts B01/B02, security policies |
| `esp32_firmware/esp32_firmware.ino` | Reads sensors, drives LEDs/buzzer, uploads to Supabase |
| `app.py` | Flask backend (one JSON endpoint `/api/dashboard`) |
| `static/` | Frontend: `index.html`, `style.css`, `app.js` (plain HTML/CSS/JS, no Streamlit) |
| `ml_model.py` | Scikit-learn time-to-full prediction |
| `route_planner.py` | Route from fixed coordinates of full bins |
| `config.py` | Thresholds, depot location, ML settings |
| `seed_demo_data.py` | Creates clearly flagged **simulated** history for demo |

## 2. Wiring

Power the ESP32 from USB (the VIN pin then supplies 5 V for the HC-SR04).

| Component | Pin | Connects to | Why |
|---|---|---|---|
| HC-SR04 #1 (Bin 1) | VCC | ESP32 VIN (5V) | Sensor needs 5 V |
| | GND | ESP32 GND | Common ground |
| | TRIG | GPIO 5 | 3.3 V output is enough to trigger |
| | ECHO | Voltage divider → GPIO 18 | ECHO is 5 V, ESP32 pins tolerate only 3.3 V |
| HC-SR04 #2 (Bin 2) | VCC / GND | VIN / GND | Same as above |
| | TRIG | GPIO 19 | |
| | ECHO | Voltage divider → GPIO 21 | |
| Green LED | Anode (long leg) | 220 Ω → GPIO 25 | Resistor limits current |
| | Cathode | GND | |
| Red LED | Anode | 220 Ω → GPIO 26 | |
| | Cathode | GND | |
| Buzzer (active) | + | GPIO 27 | |
| | − | GND | |

**Voltage divider (build once per ECHO pin):**

```
HC-SR04 ECHO ──[ 1 kΩ ]──┬── ESP32 GPIO (18 or 21)
                         │
                       [ 2 kΩ ]   (or two 1 kΩ in series)
                         │
                        GND
```
GPIO voltage = 5 V × 2k / (1k + 2k) ≈ **3.3 V**. If you only have 10 kΩ/20 kΩ the same ratio works.

Notes: use an **active** buzzer (beeps when HIGH). A passive buzzer would need `tone()`. All grounds (sensors, LEDs, buzzer, ESP32) must be joined on the breadboard GND rail.

## 3. Setup

**Supabase**
1. Create a project at supabase.com. Open *SQL Editor*, paste `supabase_schema.sql`, Run.
2. Edit the two rows in `bins` with your real coordinates (Table Editor).
3. *Project Settings → API*: copy the **Project URL**, the **anon key** (for ESP32) and the **service_role key** (for dashboard only; never put it in the ESP32 or on GitHub).

**ESP32**
1. Arduino IDE → install *ESP32 by Espressif* in Boards Manager → select *ESP32 Dev Module*.
2. Open `esp32_firmware.ino`, fill Wi-Fi name/password, `SUPABASE_URL`, `SUPABASE_ANON_KEY`.
3. Measure your model bin: set `BIN_DEPTH_CM` (sensor to floor when empty) and `MIN_DISTANCE_CM` (sensor to waste when full, keep ≥ 3 cm, the sensor cannot read below ~2 cm).
4. Upload, open Serial Monitor at 115200. You should see `Upload HTTP code: 201`.

**Dashboard**
```bash
pip install -r requirements.txt
cp .env.example .env        # fill in URL + service_role key
python app.py               # open http://localhost:5000
```

**Demo history (optional)**
```bash
export SUPABASE_URL=...  SUPABASE_SERVICE_KEY=...
python seed_demo_data.py          # 48 h simulated data, flagged is_simulated = true
python seed_demo_data.py --clear  # remove it when you have enough real data
```
State clearly in your report/viva that this history is simulated.

## 4. Logic

- **Fill %** = (BIN_DEPTH − distance) / (BIN_DEPTH − MIN_DISTANCE) × 100, clamped to 0–100. Distance is the median of 5 pings to remove spikes.
- **Status:** 0–49 NORMAL, 50–79 MEDIUM, 80–100 FULL (edit in `config.py` **and** the `.ino`).
- **LEDs/buzzer (shared):** any bin FULL → red LED + 3 beeps each cycle; otherwise green LED. The dashboard shows each bin separately.
- **Upload:** one HTTPS POST every `SEND_INTERVAL_MS` (default 20 s) carrying both bins. The database adds the timestamp.
- **Collection decision:** the dashboard selects bins whose latest reading has `collection_required = true`. Bin 1 = 92 %, Bin 2 = 45 % → only Bin 1 is routed. Both ≥ 80 % → both are visited.
- **Route:** depot → full bins, using the fixed coordinates from the `bins` table. With two bins all orders are tried and the shortest is chosen (straight-line distance). An optional "Open directions" button opens real road directions in Google Maps.

## 5. ML prediction

- **Data:** past `bin_readings` (timestamp + fill %) for one bin, last 12 h.
- **Preparation:** readings are averaged into 2-minute steps. If fill suddenly falls by ≥ 30 %, the bin was emptied, so only data after that point (the current fill cycle) is used.
- **Feature:** hours elapsed since the cycle started. **Target:** fill %.
- **Model:** `LinearRegression` fits `fill = rate × time + c`. The slope is the fill rate in % per hour.
- **Prediction:** `time_to_full = (80 − current_fill) / rate`, and `predicted_fill` after 1 hour = `current + rate × 1`.
- **Training / new readings:** the model is small, so it is re-fitted every dashboard refresh on the newest data. Each new ESP32 reading therefore updates the rate automatically. Results are saved to `predictions` (at most every 5 min per bin).
- **Limits:** it assumes a roughly steady fill rate. Real waste is thrown in bursts, so the result is an **approximate estimate**, not an exact time. If there is too little data or the bin isn't filling, the dashboard says "Unknown" instead of guessing.

## 6. Demo script

1. Start dashboard with both bins low → "No bin needs collection".
2. Put your hand/object near Bin 1's sensor (≥ 80 % fill) → red LED, buzzer, dashboard shows Bin 1 route.
3. Do the same for Bin 2 → route visits both bins.
4. Remove objects → green LED, status returns to normal.

## 7. Limitations / future scope

- HTTPS uses `setInsecure()` (encrypted, but server certificate not verified). For production, pin the Supabase root CA.
- Route uses straight-line distance for ordering; real road distance would need a routing API.
- Future scope (not required for prototype): GPS on the van, more bins, solar power, SMS alerts, per-bin LEDs.
