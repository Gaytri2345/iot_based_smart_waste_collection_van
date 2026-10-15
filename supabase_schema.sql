-- IoT-Based Smart Waste Collection Van : Supabase schema
-- Run this whole file in Supabase -> SQL Editor -> New query -> Run

-- 1. BINS : fixed locations, entered once ---------------------------------
create table if not exists bins (
  id         bigint generated always as identity primary key,
  bin_id     text unique not null,
  bin_name   text not null,
  latitude   double precision not null,
  longitude  double precision not null,
  created_at timestamptz default now()
);

-- 2. BIN_READINGS : history sent by the ESP32 (also used for ML) -----------
create table if not exists bin_readings (
  id                  bigint generated always as identity primary key,
  bin_id              text not null references bins(bin_id),
  distance_cm         real,
  fill_percentage     real,
  status              text,                    -- NORMAL / MEDIUM / FULL
  collection_required boolean default false,
  timestamp           timestamptz default now(), -- set by the database
  is_simulated        boolean default false      -- true only for seed/demo data
);
create index if not exists idx_readings_bin_time on bin_readings (bin_id, timestamp desc);

-- 3. PREDICTIONS : output of the ML model ---------------------------------
create table if not exists predictions (
  id                     bigint generated always as identity primary key,
  bin_id                 text not null references bins(bin_id),
  current_fill           real,
  predicted_fill         real,                 -- fill % expected after 1 hour
  predicted_time_to_full real,                 -- HOURS until full threshold (null = unknown)
  prediction_timestamp   timestamptz default now()
);
create index if not exists idx_pred_bin_time on predictions (bin_id, prediction_timestamp desc);

-- 4. FIXED BIN LOCATIONS (placeholders - CHANGE to your real coordinates) --
insert into bins (bin_id, bin_name, latitude, longitude) values
  ('B01', 'College Gate', 28.613900, 77.209000),
  ('B02', 'Canteen',      28.614500, 77.210200)
on conflict (bin_id) do nothing;

-- 5. SECURITY ---------------------------------------------------------------
-- ESP32 uses the ANON key  -> may ONLY insert into bin_readings.
-- Dashboard uses the SERVICE_ROLE key (kept secret, bypasses RLS).
alter table bins          enable row level security;
alter table bin_readings  enable row level security;
alter table predictions   enable row level security;

drop policy if exists "esp32 can insert readings" on bin_readings;
create policy "esp32 can insert readings"
  on bin_readings for insert to anon with check (true);
