/*
  IoT-Based Smart Waste Collection Van - ESP32 firmware
  2 x HC-SR04, green LED, red LED, buzzer -> Wi-Fi -> Supabase (HTTPS REST)

  Arduino IDE: board "ESP32 Dev Module". No extra libraries needed.
*/
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>

// ===================== USER SETTINGS (edit these) =====================
const char* WIFI_SSID         = "Redmi";
const char* WIFI_PASSWORD     = "sagar@123";
const char* SUPABASE_URL      = "https://qztjzmnxmybnrfaupizt.supabase.co";
const char* SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InF6dGp6bW54bXlibnJmYXVwaXp0Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3OTExMDkxOTcsImV4cCI6MjEwNjY4NTE5N30.Jj__dlE_6zHo02EFXiKEHNx46mmqVfaUZeWDqwc82T8";   // anon key, NOT service_role

const unsigned long SEND_INTERVAL_MS = 20000;  // 10000-30000 recommended

// Bin geometry (measure your model bins with a ruler)
const float BIN1_DEPTH_CM = 11.5;
const float BIN2_DEPTH_CM = 12.5;;  // sensor to bin floor when EMPTY  -> 0 %
const float MIN_DISTANCE_CM = 3.0;   // sensor to waste when FULL       -> 100 %

// Status thresholds (keep same as config.py)
const float MEDIUM_THRESHOLD = 50.0;
const float FULL_THRESHOLD   = 80.0;
// ======================================================================

// Pins
#define TRIG1 5
#define ECHO1 18
#define TRIG2 19
#define ECHO2 21
#define LED_GREEN 25
#define LED_RED   26
#define BUZZER    27

struct Bin {
  const char* id;
  uint8_t trig, echo;
  float distance;   // cm, -1 if sensor failed
  float fill;       // %
  const char* status;
  bool full;
};

Bin bins[2] = {
  {"B01", TRIG1, ECHO1, -1, 0, "NORMAL", false},
  {"B02", TRIG2, ECHO2, -1, 0, "NORMAL", false}
};

unsigned long lastSend = 0;

// One raw distance measurement in cm (-1 on timeout)
float singleMeasure(uint8_t trig, uint8_t echo) {
  digitalWrite(trig, LOW);  delayMicroseconds(2);
  digitalWrite(trig, HIGH); delayMicroseconds(10);
  digitalWrite(trig, LOW);
  unsigned long dur = pulseIn(echo, HIGH, 30000UL);  // 30 ms timeout (~5 m)
  if (dur == 0) return -1;
  return dur * 0.0343f / 2.0f;
}

// Median of 5 readings removes random spikes
float readDistance(uint8_t trig, uint8_t echo) {
  float v[5]; int n = 0;
  for (int i = 0; i < 5; i++) {
    float d = singleMeasure(trig, echo);
    if (d > 1.0 && d < 400.0) v[n++] = d;
    delay(60);
  }
  if (n < 3) return -1;
  for (int i = 0; i < n - 1; i++)
    for (int j = i + 1; j < n; j++)
      if (v[j] < v[i]) { float t = v[i]; v[i] = v[j]; v[j] = t; }
  return v[n / 2];
}

float distanceToFill(float d, float binDepth) {
  float f = (binDepth - d) /
            (binDepth - MIN_DISTANCE_CM) * 100.0f;
  return constrain(f, 0.0f, 100.0f);
}

const char* fillToStatus(float f) {
  if (f >= FULL_THRESHOLD)   return "FULL";
  if (f >= MEDIUM_THRESHOLD) return "MEDIUM";
  return "NORMAL";
}

void beep(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(BUZZER, HIGH); delay(150);
    digitalWrite(BUZZER, LOW);  delay(150);
  }
}

void connectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;
  Serial.print("Connecting to Wi-Fi");
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 15000) {
    delay(500); Serial.print(".");
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("\nConnected, IP: "); Serial.println(WiFi.localIP());
  } else {
    Serial.println("\nWi-Fi failed (will retry). Local LEDs/buzzer still work.");
  }
}

void sendToSupabase() {
  // Build JSON array with every bin that has a valid reading
  String body = "[";
  bool first = true;
  for (int i = 0; i < 2; i++) {
    if (bins[i].distance < 0) continue;
    if (!first) body += ",";
    first = false;
    body += "{\"bin_id\":\"" + String(bins[i].id) + "\"";
    body += ",\"distance_cm\":" + String(bins[i].distance, 1);
    body += ",\"fill_percentage\":" + String(bins[i].fill, 1);
    body += ",\"status\":\"" + String(bins[i].status) + "\"";
    body += ",\"collection_required\":" + String(bins[i].full ? "true" : "false") + "}";
  }
  body += "]";
  if (first) { Serial.println("No valid readings - nothing sent."); return; }

  if (WiFi.status() != WL_CONNECTED) { Serial.println("No Wi-Fi - skipped upload."); return; }

  WiFiClientSecure client;
  client.setInsecure();  // prototype: skips certificate check (traffic is still encrypted)
  HTTPClient http;
  String url = String(SUPABASE_URL) + "/rest/v1/bin_readings";
  http.begin(client, url);
  http.addHeader("Content-Type", "application/json");
  http.addHeader("apikey", SUPABASE_ANON_KEY);
  http.addHeader("Authorization", String("Bearer ") + SUPABASE_ANON_KEY);
  http.addHeader("Prefer", "return=minimal");
  int code = http.POST(body);
  Serial.printf("Upload HTTP code: %d (201 = OK)\n", code);
  if (code != 201) Serial.println(http.getString());
  http.end();
}

void cycle() {
  bool anyFull = false;
  for (int i = 0; i < 2; i++) {
    bins[i].distance = readDistance(bins[i].trig, bins[i].echo);
    if (bins[i].distance < 0) {
      Serial.printf("%s: sensor error\n", bins[i].id);
      bins[i].full = false;
      continue;
    }
    float depth = (i == 0) ? BIN1_DEPTH_CM : BIN2_DEPTH_CM;
bins[i].fill = distanceToFill(bins[i].distance, depth);
    bins[i].status = fillToStatus(bins[i].fill);
    bins[i].full   = bins[i].fill >= FULL_THRESHOLD;
    anyFull |= bins[i].full;
    Serial.printf("%s: %.1f cm -> %.1f %% -> %s\n",
                  bins[i].id, bins[i].distance, bins[i].fill, bins[i].status);
  }

  digitalWrite(LED_GREEN, anyFull ? LOW : HIGH);
  digitalWrite(LED_RED,   anyFull ? HIGH : LOW);
  if (anyFull) beep(3);

  connectWiFi();
  sendToSupabase();
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG1, OUTPUT); pinMode(ECHO1, INPUT);
  pinMode(TRIG2, OUTPUT); pinMode(ECHO2, INPUT);
  pinMode(LED_GREEN, OUTPUT); pinMode(LED_RED, OUTPUT); pinMode(BUZZER, OUTPUT);
  digitalWrite(LED_GREEN, HIGH);  // power-on indication
  connectWiFi();
  cycle();
  lastSend = millis();
}

void loop() {
  if (millis() - lastSend >= SEND_INTERVAL_MS) {
    lastSend = millis();
    cycle();
  }
}
