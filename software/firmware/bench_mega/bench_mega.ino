/*
 * Wet Lab Bench - Arduino Mega 2560 firmware ("WLB-MEGA v1").
 *
 * Implements the JSON-line protocol of software/bench/hal/protocol.py on the pin table of
 * docs/electrical.md:
 *   D2  e-stop pole 2 (INPUT_PULLUP, NC to GND; HIGH = pressed or broken -> latched fault)
 *   D3  HX711 DT        D4  HX711 SCK   (80 SPS: RATE pin tied high on the board)
 *   D6  carousel servo PWM (Timer4 OC4A)   D7 stage servo (OC4B)   D8 auger FB5311M-360 (OC4C)
 *   A2  auger position feedback (0..~3.3 V over one revolution)
 *   USB 250000 baud, open with DTR/RTS low so the Mega does not reset.
 *
 * No Servo library: Timer4 in mode 14 (fast PWM, TOP = ICR4 = 39999, prescaler 8) gives a
 * 20 ms frame with OCR4x = 2 * microseconds.  All three outputs stay LOW until commanded.
 *
 * Host commands (one JSON object per line):
 *   {"id":n,"cmd":"ver"} {"id":n,"cmd":"weight"} {"id":n,"cmd":"stream","on":true}
 *   {"id":n,"cmd":"carousel","deg":180,"ms":4000} {"id":n,"cmd":"stage","deg":150,"ms":2500}
 *   {"id":n,"cmd":"auger","rev":3.5,"dir":1} {"id":n,"cmd":"status"} {"id":n,"cmd":"stop"}
 *   {"id":n,"cmd":"clr"} {"id":n,"cmd":"hb"}
 * Replies {"id":n,"ok":true,...} / {"id":n,"ok":false,"err":"RANGE"}; completions {"done":n};
 * unsolicited {"w":[millis,grams]} at the HX711 rate, {"f":"ESTOP"|"AUGER_JAM"|"WDT"|"HX_TIMEOUT"}.
 *
 * Calibration constants below (SERVO_* microsecond endpoints, COUNTS_PER_G, AUGER_STOP_US)
 * must be measured on the bench (electrical.md 10, tests E7/E8/E10) and edited here.
 */

#include <avr/wdt.h>

// ---------------------------------------------------------------- pins
const uint8_t PIN_ESTOP = 2;
const uint8_t PIN_HX_DT = 3;
const uint8_t PIN_HX_SCK = 4;
const uint8_t PIN_CAROUSEL = 6;   // OC4A
const uint8_t PIN_STAGE = 7;      // OC4B
const uint8_t PIN_AUGER = 8;      // OC4C
const uint8_t PIN_AUGER_FB = A2;

// ---------------------------------------------------------------- calibration (EDIT ON THE BENCH)
float COUNTS_PER_G = 420.0f;          // HX711 counts per gram, from a 100 g class-M2 weight
long  HX_OFFSET = 0;                  // raw counts at power-up (the host tares; this just centres)
// carousel: degrees -> microseconds.  M45CHW ~ 500..2500 us over its travel; measure.
const float CAROUSEL_US_PER_DEG = 2000.0f / 270.0f;
const int   CAROUSEL_US_ZERO = 1500;
const int   CAROUSEL_US_MIN = 500, CAROUSEL_US_MAX = 2500;
// stage: crank 0..150 deg -> WORK..ERUPT pulses (commission with the printed gauge, test E10)
const int   STAGE_US_WORK = 900;
const int   STAGE_US_ERUPT = 2000;
// auger continuous servo: stop centre and speed offset
const int   AUGER_STOP_US = 1500;
const int   AUGER_RUN_OFFSET_US = 200;
const float AUGER_FB_V_PER_REV = 3.3f;   // feedback volts over one revolution (measure, must be < 5 V)

// ---------------------------------------------------------------- limits (protocol.py LIMITS)
const float CAROUSEL_DEG_MIN = -720, CAROUSEL_DEG_MAX = 720;
const float STAGE_DEG_MIN = 0, STAGE_DEG_MAX = 150;
const float AUGER_REV_MAX = 50;
const unsigned long COMM_WATCHDOG_MS = 500;
const unsigned long HX_TIMEOUT_MS = 100;

// ---------------------------------------------------------------- state
struct Move { bool active; float q0, q1; unsigned long t0, dur; int id; };
Move carousel = {false, 0, 0, 0, 0, 0};
Move stage = {false, 0, 0, 0, 0, 0};
float carouselDeg = 0, stageDeg = 0;
bool augerActive = false; int augerId = 0; int augerDir = 1;
float augerRevTarget = 0, augerRevDone = 0;
float augerAngle = 0;        // unwrapped feedback, degrees
float augerLastFb = 0;
unsigned long augerStallT0 = 0; float augerStallAngle = 0; int augerStalls = 0;
bool streaming = false;
char fault[16] = "";          // "" = none; latched until clr
unsigned long lastHostMs = 0, lastHxMs = 0;
long lastRaw = 0; float lastGrams = 0;
char line[160]; uint8_t lineLen = 0;

// ---------------------------------------------------------------- servo PWM (Timer4)
void pwmInit() {
  pinMode(PIN_CAROUSEL, OUTPUT); pinMode(PIN_STAGE, OUTPUT); pinMode(PIN_AUGER, OUTPUT);
  digitalWrite(PIN_CAROUSEL, LOW); digitalWrite(PIN_STAGE, LOW); digitalWrite(PIN_AUGER, LOW);
  TCCR4A = 0; TCCR4B = 0;
  ICR4 = 39999;                                   // 20 ms at 16 MHz / 8
  TCCR4A = (1 << WGM41);
  TCCR4B = (1 << WGM43) | (1 << WGM42) | (1 << CS41);   // mode 14, prescaler 8
  OCR4A = 0; OCR4B = 0; OCR4C = 0;                // outputs disconnected until commanded
}
void pwmSet(uint8_t pin, int us) {                 // us == 0 -> output off
  if (pin == PIN_CAROUSEL) { if (us) { OCR4A = 2L * us; TCCR4A |= (1 << COM4A1); } else { TCCR4A &= ~(1 << COM4A1); digitalWrite(pin, LOW); } }
  if (pin == PIN_STAGE)    { if (us) { OCR4B = 2L * us; TCCR4A |= (1 << COM4B1); } else { TCCR4A &= ~(1 << COM4B1); digitalWrite(pin, LOW); } }
  if (pin == PIN_AUGER)    { if (us) { OCR4C = 2L * us; TCCR4A |= (1 << COM4C1); } else { TCCR4A &= ~(1 << COM4C1); digitalWrite(pin, LOW); } }
}
void allPwmOff() { pwmSet(PIN_CAROUSEL, 0); pwmSet(PIN_STAGE, 0); pwmSet(PIN_AUGER, 0); augerActive = false; carousel.active = stage.active = false; }

int carouselUs(float deg) { return constrain((int)(CAROUSEL_US_ZERO + deg * CAROUSEL_US_PER_DEG), CAROUSEL_US_MIN, CAROUSEL_US_MAX); }
int stageUs(float deg) { return (int)(STAGE_US_WORK + (STAGE_US_ERUPT - STAGE_US_WORK) * (deg / 150.0f)); }

// ---------------------------------------------------------------- HX711 (direct port, 25 clocks)
bool hxReady() { return digitalRead(PIN_HX_DT) == LOW; }
long hxRead() {
  long v = 0;
  noInterrupts();
  for (uint8_t i = 0; i < 24; i++) {
    digitalWrite(PIN_HX_SCK, HIGH); delayMicroseconds(1);
    v = (v << 1) | digitalRead(PIN_HX_DT);
    digitalWrite(PIN_HX_SCK, LOW); delayMicroseconds(1);
  }
  digitalWrite(PIN_HX_SCK, HIGH); delayMicroseconds(1); digitalWrite(PIN_HX_SCK, LOW);   // gain 128
  interrupts();
  if (v & 0x800000L) v |= 0xFF000000L;
  return v;
}

// ---------------------------------------------------------------- faults
void raiseFault(const char* code) {
  if (fault[0]) return;
  strncpy(fault, code, sizeof(fault) - 1);
  allPwmOff();
  Serial.print(F("{\"f\":\"")); Serial.print(fault); Serial.println(F("\"}"));
}

// ---------------------------------------------------------------- tiny JSON helpers
bool jsonStr(const char* s, const char* key, char* out, size_t n) {
  char pat[24]; snprintf(pat, sizeof(pat), "\"%s\":\"", key);
  const char* p = strstr(s, pat); if (!p) return false;
  p += strlen(pat); size_t i = 0;
  while (*p && *p != '"' && i < n - 1) out[i++] = *p++;
  out[i] = 0; return true;
}
bool jsonNum(const char* s, const char* key, float* out) {
  char pat[24]; snprintf(pat, sizeof(pat), "\"%s\":", key);
  const char* p = strstr(s, pat); if (!p) return false;
  *out = atof(p + strlen(pat)); return true;
}
bool jsonBool(const char* s, const char* key, bool* out) {
  char pat[24]; snprintf(pat, sizeof(pat), "\"%s\":", key);
  const char* p = strstr(s, pat); if (!p) return false;
  *out = strncmp(p + strlen(pat), "true", 4) == 0; return true;
}
void ok(int id) { Serial.print(F("{\"id\":")); Serial.print(id); Serial.println(F(",\"ok\":true}")); }
void err(int id, const char* code) { Serial.print(F("{\"id\":")); Serial.print(id); Serial.print(F(",\"ok\":false,\"err\":\"")); Serial.print(code); Serial.println(F("\"}")); }
void done(int id) { Serial.print(F("{\"done\":")); Serial.print(id); Serial.println(F("}")); }

// ---------------------------------------------------------------- commands
void handle(const char* s) {
  lastHostMs = millis();
  float fid = 0; jsonNum(s, "id", &fid); int id = (int)fid;
  char cmd[16]; if (!jsonStr(s, "cmd", cmd, sizeof(cmd))) { err(id, "UNKNOWN"); return; }
  bool busy = carousel.active || stage.active || augerActive;

  if (!strcmp(cmd, "hb")) { ok(id); return; }
  if (!strcmp(cmd, "ver")) { Serial.print(F("{\"id\":")); Serial.print(id); Serial.println(F(",\"ok\":true,\"fw\":\"WLB-MEGA v1\",\"hx_hz\":80}")); return; }
  if (!strcmp(cmd, "weight")) { Serial.print(F("{\"id\":")); Serial.print(id); Serial.print(F(",\"ok\":true,\"g\":")); Serial.print(lastGrams, 3); Serial.print(F(",\"ms\":")); Serial.print(lastHxMs); Serial.println(F("}")); return; }
  if (!strcmp(cmd, "stream")) { bool on = true; jsonBool(s, "on", &on); streaming = on; ok(id); return; }
  if (!strcmp(cmd, "status")) {
    Serial.print(F("{\"id\":")); Serial.print(id); Serial.print(F(",\"ok\":true,\"estop\":")); Serial.print(digitalRead(PIN_ESTOP) == HIGH ? "true" : "false");
    Serial.print(F(",\"fault\":")); if (fault[0]) { Serial.print('"'); Serial.print(fault); Serial.print('"'); } else Serial.print(F("null"));
    Serial.print(F(",\"carousel_deg\":")); Serial.print(carouselDeg, 1); Serial.print(F(",\"stage_deg\":")); Serial.print(stageDeg, 1);
    Serial.print(F(",\"auger_rev\":")); Serial.print(augerAngle / 360.0f, 3);
    Serial.print(F(",\"busy\":[")); bool first = true;
    if (carousel.active) { Serial.print(F("\"carousel\"")); first = false; }
    if (stage.active) { if (!first) Serial.print(','); Serial.print(F("\"stage\"")); first = false; }
    if (augerActive) { if (!first) Serial.print(','); Serial.print(F("\"auger\"")); }
    Serial.println(F("]}")); return;
  }
  if (!strcmp(cmd, "stop")) { allPwmOff(); ok(id); return; }
  if (!strcmp(cmd, "clr")) { if (digitalRead(PIN_ESTOP) == HIGH) { err(id, "ESTOP"); return; } fault[0] = 0; augerStalls = 0; ok(id); return; }
  if (fault[0]) { err(id, strcmp(fault, "ESTOP") == 0 ? "ESTOP" : "STATE"); return; }

  if (!strcmp(cmd, "carousel") || !strcmp(cmd, "stage")) {
    float deg, ms; if (!jsonNum(s, "deg", &deg) || !jsonNum(s, "ms", &ms)) { err(id, "RANGE"); return; }
    bool isC = cmd[0] == 'c';
    if (isC ? (deg < CAROUSEL_DEG_MIN || deg > CAROUSEL_DEG_MAX || ms < 500 || ms > 60000)
            : (deg < STAGE_DEG_MIN || deg > STAGE_DEG_MAX || ms < 1500 || ms > 20000)) { err(id, "RANGE"); return; }
    if (busy) { err(id, "BUSY"); return; }
    Move& mv = isC ? carousel : stage;
    mv.active = true; mv.q0 = isC ? carouselDeg : stageDeg; mv.q1 = deg; mv.t0 = millis(); mv.dur = (unsigned long)ms; mv.id = id;
    ok(id); return;
  }
  if (!strcmp(cmd, "auger")) {
    float rev, dir = 1; if (!jsonNum(s, "rev", &rev)) { err(id, "RANGE"); return; } jsonNum(s, "dir", &dir);
    if (rev < 0 || rev > AUGER_REV_MAX) { err(id, "RANGE"); return; }
    if (busy) { err(id, "BUSY"); return; }
    augerActive = true; augerId = id; augerDir = dir >= 0 ? 1 : -1; augerRevTarget = rev; augerRevDone = 0;
    augerStallT0 = millis(); augerStallAngle = augerAngle; augerStalls = 0;
    pwmSet(PIN_AUGER, AUGER_STOP_US + augerDir * AUGER_RUN_OFFSET_US);
    ok(id); return;
  }
  err(id, "UNKNOWN");
}

// ---------------------------------------------------------------- loop pieces
void serviceMoves() {
  unsigned long now = millis();
  Move* mvs[2] = {&carousel, &stage};
  for (int i = 0; i < 2; i++) {
    Move& mv = *mvs[i]; if (!mv.active) continue;
    float u = mv.dur ? (float)(now - mv.t0) / mv.dur : 1.0f; if (u > 1) u = 1;
    float sm = u * u * (3 - 2 * u);
    float q = mv.q0 + (mv.q1 - mv.q0) * sm;
    if (i == 0) { carouselDeg = q; pwmSet(PIN_CAROUSEL, carouselUs(q)); }
    else { stageDeg = q; pwmSet(PIN_STAGE, stageUs(q)); }
    if (u >= 1) { mv.active = false; done(mv.id); }
  }
}
void serviceAuger() {
  // unwrap the feedback angle (0..360 over AUGER_FB_V_PER_REV volts)
  float v = analogRead(PIN_AUGER_FB) * 5.0f / 1023.0f;
  float a = fmod(v / AUGER_FB_V_PER_REV * 360.0f, 360.0f);
  float d = a - augerLastFb; if (d > 180) d -= 360; if (d < -180) d += 360;
  augerAngle += d; augerLastFb = a;
  if (!augerActive) return;
  augerRevDone = fabs(augerAngle - augerStallAngle) / 360.0f;   // progress since start/retry
  // stall rule (electrical.md 6): < 5 deg progress in 150 ms -> stop, reverse 1/4 turn, retry; 3 -> fault
  static float winAngle = 0; static unsigned long winT = 0;
  if (millis() - winT >= 150) {
    if (fabs(augerAngle - winAngle) < 5.0f && millis() - augerStallT0 > 150) {
      augerStalls++;
      if (augerStalls >= 3) { raiseFault("AUGER_JAM"); return; }
      pwmSet(PIN_AUGER, AUGER_STOP_US - augerDir * AUGER_RUN_OFFSET_US); delay(120);   // ~1/4 turn back
      pwmSet(PIN_AUGER, AUGER_STOP_US + augerDir * AUGER_RUN_OFFSET_US);
    }
    winAngle = augerAngle; winT = millis();
  }
  if (augerRevDone >= augerRevTarget) {
    pwmSet(PIN_AUGER, 0); augerActive = false;
    Serial.print(F("{\"done\":")); Serial.print(augerId); Serial.print(F(",\"rev\":")); Serial.print(augerRevDone, 3); Serial.println(F("}"));
  }
}
void serviceScale() {
  if (hxReady()) {
    lastRaw = hxRead(); lastHxMs = millis();
    lastGrams = (lastRaw - HX_OFFSET) / COUNTS_PER_G;
    if (streaming) { Serial.print(F("{\"w\":[")); Serial.print(lastHxMs); Serial.print(','); Serial.print(lastGrams, 3); Serial.println(F("]}")); }
  } else if (millis() - lastHxMs > HX_TIMEOUT_MS && lastHxMs) {
    raiseFault("HX_TIMEOUT");
  }
}

void setup() {
  pinMode(PIN_ESTOP, INPUT_PULLUP);
  pinMode(PIN_HX_DT, INPUT); pinMode(PIN_HX_SCK, OUTPUT); digitalWrite(PIN_HX_SCK, LOW);
  pwmInit();
  Serial.begin(250000);
  delay(50);
  while (!hxReady()) { if (millis() > 2000) break; }
  if (hxReady()) HX_OFFSET = hxRead();
  Serial.println(F("{\"i\":{\"fw\":\"WLB-MEGA v1\",\"hx_hz\":80}}"));
  lastHostMs = millis();
  wdt_enable(WDTO_250MS);
}

void loop() {
  wdt_reset();
  // e-stop (NC to GND; HIGH = pressed or wire broken)
  if (digitalRead(PIN_ESTOP) == HIGH) raiseFault("ESTOP");
  // host link watchdog
  if (millis() - lastHostMs > COMM_WATCHDOG_MS) raiseFault("WDT");
  // serial lines
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') { if (lineLen) { line[lineLen] = 0; handle(line); lineLen = 0; } }
    else if (lineLen < sizeof(line) - 1) line[lineLen++] = c;
    else lineLen = 0;
  }
  serviceScale();
  serviceMoves();
  serviceAuger();
}
