// Wet Lab Bench Mega firmware core: see protocol_core.h. No Arduino headers.
#include "protocol_core.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

namespace wlb {

static const size_t CRC_TAIL = 12;                     // len(',"crc":"00"}'), protocol.CRC_TAIL
static const char HEX[] = "0123456789abcdef";

// ------------------------------------------------------------------ CRC and names
uint8_t crc8(const char* data, size_t n) {
    uint8_t c = 0;
    for (size_t i = 0; i < n; i++) {
        c ^= (uint8_t)data[i];
        for (uint8_t b = 0; b < 8; b++) c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
    }
    return c;
}

static const char* const ERR_NAMES[] = {"", "BADCMD", "RANGE", "BUSY", "STATE", "ESTOP", "CRC"};
static const char* const FAULT_NAMES[] = {"ESTOP", "AUGER_JAM", "HOPPER_EMPTY", "HX_TIMEOUT",
                                          "WDT", "TT_TIMEOUT", "ST_TIMEOUT", "AUG_TIMEOUT"};

const char* err_name(int e) { return (e > 0 && e <= E_CRC) ? ERR_NAMES[e] : ""; }

const char* fault_name(uint16_t f) {
    for (uint8_t i = 0; i < 8; i++)
        if (f == (uint16_t)(1u << i)) return FAULT_NAMES[i];
    return "?";
}

// ------------------------------------------------------------------ small text helpers
static bool finite_(float v) { return v == v && v - v == 0.0f; }   // false for NaN and +-inf
static char lower_(char c) { return (c >= 'A' && c <= 'Z') ? (char)(c - 'A' + 'a') : c; }
static bool digit_(char c) { return c >= '0' && c <= '9'; }

static size_t fmt_u32(char* out, uint32_t v) {          // out needs 11 bytes
    char t[10];
    size_t n = 0, k = 0;
    do { t[n++] = (char)('0' + v % 10); v /= 10; } while (v);
    while (n) out[k++] = t[--n];
    out[k] = 0;
    return k;
}

static size_t fmt_i32(char* out, int32_t v) {           // out needs 12 bytes
    if (v >= 0) return fmt_u32(out, (uint32_t)v);
    out[0] = '-';
    return 1 + fmt_u32(out + 1, 0u - (uint32_t)v);
}

size_t fmt_num(char* out, size_t cap, float v, uint8_t decimals) {
    char t[40];
    size_t n = 0;
    if (!finite_(v)) {
        const char* s = (v != v) ? "nan" : (v > 0 ? "inf" : "-inf");
        while (*s) t[n++] = *s++;
    } else {
        if (decimals > 6) decimals = 6;
        bool neg = v < 0;
        float a = neg ? -v : v;
        uint32_t scale = 1;
        for (uint8_t i = 0; i < decimals; i++) scale *= 10;
        while (decimals && a * (float)scale >= 4.0e9f) { decimals--; scale /= 10; }
        if (a >= 4.0e9f) {                              // out of fixed-point range: d.ddde+XX
            int e = 0;
            while (a >= 10.0f && e < 60) { a /= 10.0f; e++; }
            uint32_t q = (uint32_t)(a * 1000.0f + 0.5f);
            if (neg) t[n++] = '-';
            t[n++] = (char)('0' + q / 1000); t[n++] = '.';
            t[n++] = (char)('0' + q / 100 % 10); t[n++] = (char)('0' + q / 10 % 10); t[n++] = (char)('0' + q % 10);
            t[n++] = 'e'; t[n++] = '+';
            n += fmt_u32(t + n, (uint32_t)e);
        } else {
            uint32_t q = (uint32_t)(a * (float)scale + 0.5f);
            if (neg && q) t[n++] = '-';
            n += fmt_u32(t + n, q / scale);
            if (decimals) {
                uint32_t frac = q % scale;
                char d[8];
                for (int i = decimals - 1; i >= 0; i--) { d[i] = (char)('0' + frac % 10); frac /= 10; }
                int keep = decimals;
                while (keep > 1 && d[keep - 1] == '0') keep--;
                t[n++] = '.';
                for (int i = 0; i < keep; i++) t[n++] = d[i];
            }
        }
    }
    size_t k = 0;
    if (cap == 0) return 0;
    for (; k < n && k + 1 < cap; k++) out[k] = t[k];
    out[k] = 0;
    return k;
}

namespace {
struct Sb {                                             // bounded string builder for detail texts
    char* p;
    size_t cap, n;
    Sb(char* buf, size_t c) : p(buf), cap(c), n(0) { if (cap) p[0] = 0; }
    Sb& s(const char* t) {
        while (*t && n + 1 < cap) p[n++] = *t++;
        if (cap) p[n] = 0;
        return *this;
    }
    Sb& f(float v, uint8_t d) { char t[24]; fmt_num(t, sizeof t, v, d); return s(t); }
    Sb& i(int32_t v) { char t[12]; fmt_i32(t, v); return s(t); }
};
}  // namespace

// ------------------------------------------------------------------ flat JSON
const Value* FlatObject::get(const char* key) const {
    for (uint8_t i = 0; i < n; i++)
        if (strcmp(keys[i], key) == 0) return &vals[i];
    return 0;
}

namespace {
struct Parser {
    const char* s;
    size_t n, i;
    const char* err;

    bool fail(const char* e) { if (!err) err = e; return false; }
    void ws() { while (i < n && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r')) i++; }
    bool at(char c) const { return i < n && s[i] == c; }

    bool lit(const char* t) {
        size_t k = strlen(t);
        if (n - i < k || memcmp(s + i, t, k) != 0) return fail("bad literal");
        i += k;
        return true;
    }

    bool str(char* out, size_t cap) {                   // at the opening quote; cap excludes the NUL
        i++;
        size_t o = 0;
        for (;;) {
            if (i >= n) return fail("unterminated string");
            char c = s[i++];
            if (c == '"') break;
            if ((uint8_t)c < 0x20) return fail("control character in string");
            if (c == '\\') {
                if (i >= n) return fail("bad escape");
                char e = s[i++];
                switch (e) {
                case '"': c = '"'; break;
                case '\\': c = '\\'; break;
                case '/': c = '/'; break;
                case 'b': c = '\b'; break;
                case 'f': c = '\f'; break;
                case 'n': c = '\n'; break;
                case 'r': c = '\r'; break;
                case 't': c = '\t'; break;
                case 'u': {
                    if (n - i < 4) return fail("bad escape");
                    uint16_t v = 0;
                    for (int k = 0; k < 4; k++) {
                        char h = lower_(s[i++]);
                        uint8_t d;
                        if (digit_(h)) d = (uint8_t)(h - '0');
                        else if (h >= 'a' && h <= 'f') d = (uint8_t)(h - 'a' + 10);
                        else return fail("bad escape");
                        v = (uint16_t)(v * 16 + d);
                    }
                    if (v == 0 || v >= 0x80) return fail("non-ASCII escape");
                    c = (char)v;
                    break;
                }
                default: return fail("bad escape");
                }
            }
            if (o >= cap) return fail("string too long");
            out[o++] = c;
        }
        out[o] = 0;
        return true;
    }

    bool number(Value& v) {                             // JSON number grammar, as Python's json accepts it
        size_t st = i;
        bool real = false;
        if (at('-')) i++;
        if (at('0')) i++;
        else if (i < n && s[i] >= '1' && s[i] <= '9') { while (i < n && digit_(s[i])) i++; }
        else return fail("bad number");
        if (at('.')) {
            real = true; i++;
            if (i >= n || !digit_(s[i])) return fail("bad number");
            while (i < n && digit_(s[i])) i++;
        }
        if (at('e') || at('E')) {
            real = true; i++;
            if (at('+') || at('-')) i++;
            if (i >= n || !digit_(s[i])) return fail("bad number");
            while (i < n && digit_(s[i])) i++;
        }
        size_t len = i - st;
        if (len > 31) return fail("number too long");
        char t[32];
        memcpy(t, s + st, len);
        t[len] = 0;
        v.f = (float)strtod(t, 0);
        v.type = V_NUM;
        if (!real) {                                    // integer literal: exact when it fits int32
            bool neg = t[0] == '-';
            uint32_t acc = 0;
            bool over = false;
            for (size_t k = neg ? 1 : 0; k < len; k++) {
                uint32_t d = (uint32_t)(t[k] - '0');
                if (acc > 429496729u || (acc == 429496729u && d > 5)) over = true;
                acc = acc * 10 + d;
            }
            if (!over && acc <= (neg ? 2147483648u : 2147483647u)) {
                v.type = V_INT;
                v.i = neg ? (int32_t)(0u - acc) : (int32_t)acc;
                v.f = (float)v.i;
            }
        }
        return true;
    }
};
}  // namespace

bool parse_flat_json(const char* s, size_t n, FlatObject& out, const char** err) {
    Parser p;
    p.s = s; p.n = n; p.i = 0; p.err = 0;
    out.n = 0;
    p.ws();
    if (!p.at('{')) { *err = "not a JSON object"; return false; }
    p.i++;
    p.ws();
    if (p.at('}')) {
        p.i++;
    } else {
        for (;;) {
            if (!p.at('"')) { p.fail("expected a key"); break; }
            char key[KEY_MAX + 1];
            if (!p.str(key, KEY_MAX)) break;
            p.ws();
            if (!p.at(':')) { p.fail("expected :"); break; }
            p.i++;
            p.ws();
            Value v;
            memset(&v, 0, sizeof v);
            bool ok;
            if (p.at('"')) { v.type = V_STR; ok = p.str(v.s, STR_MAX); }
            else if (p.at('t')) { v.type = V_BOOL; v.b = true; v.i = 1; v.f = 1.0f; ok = p.lit("true"); }
            else if (p.at('f')) { v.type = V_BOOL; ok = p.lit("false"); }
            else if (p.at('n')) { v.type = V_NULL; ok = p.lit("null"); }
            else if (p.at('-') || (p.i < n && digit_(s[p.i]))) ok = p.number(v);
            else if (p.at('{') || p.at('[')) ok = p.fail("nested values are not supported");
            else ok = p.fail("bad value");
            if (!ok) break;
            uint8_t slot = out.n;
            for (uint8_t k = 0; k < out.n; k++)
                if (strcmp(out.keys[k], key) == 0) slot = k;
            if (slot == out.n) {
                if (out.n >= MAX_KEYS) { p.fail("too many keys"); break; }
                out.n++;
            }
            memcpy(out.keys[slot], key, sizeof key);
            out.vals[slot] = v;
            p.ws();
            if (p.at(',')) { p.i++; p.ws(); continue; }
            if (p.at('}')) { p.i++; break; }
            p.fail("expected , or }");
            break;
        }
    }
    if (!p.err) {
        p.ws();
        if (p.i != n) p.fail("extra data");
    }
    if (p.err) { *err = p.err; out.n = 0; return false; }
    return true;
}

static bool space_(char c) {                            // Python str.strip() whitespace (ASCII part)
    return c == ' ' || (c >= '\t' && c <= '\r') || (c >= 0x1c && c <= 0x1f);
}

int decode_line(const char* line, size_t n, FlatObject& out, char* detail, size_t detail_n) {
    Sb d(detail, detail_n);
    size_t a = 0, b = n;
    while (a < b && space_(line[a])) a++;
    while (b > a && space_(line[b - 1])) b--;
    const char* L = line + a;
    size_t m = b - a;
    if (m > IN_MAX) { d.s("line too long"); return E_BADCMD; }
    char body[IN_MAX + 2];
    size_t bl;
    // protocol.decode: line.endswith('"}') and line[-12:].startswith(',"crc":"')
    size_t ts = m >= CRC_TAIL ? m - CRC_TAIL : 0;
    if (m >= 2 && L[m - 2] == '"' && L[m - 1] == '}' && m - ts >= 8 && memcmp(L + ts, ",\"crc\":\"", 8) == 0) {
        bl = ts;
        memcpy(body, L, bl);
        body[bl++] = '}';
        size_t c0 = m >= 4 ? m - 4 : 0, c1 = m - 2;      // line[-4:-2]
        uint8_t c = crc8(body, bl);
        bool match = c1 - c0 == 2 && lower_(L[c0]) == HEX[c >> 4] && lower_(L[c0 + 1]) == HEX[c & 15];
        if (!match) {
            char got[3] = {0, 0, 0};
            for (size_t k = c0; k < c1 && k - c0 < 2; k++) got[k - c0] = (L[k] == '"' || L[k] == '\\') ? '?' : L[k];
            d.s("got ").s(got);
            return E_CRC;
        }
    } else {
        bl = m;
        memcpy(body, L, m);                             // CRC is optional for hand-typed bench commands
    }
    body[bl] = 0;
    const char* err = "";
    if (!parse_flat_json(body, bl, out, &err)) { d.s("not JSON: ").s(err); return E_BADCMD; }
    return E_NONE;
}

// ------------------------------------------------------------------ writer
void Writer::begin(char* buf, size_t cap) {
    buf_ = buf; cap_ = cap; n_ = 0; ok_ = true; sorted = true; last_[0] = 0;
    putc_('{');
}

void Writer::putc_(char c) {
    if (n_ + 1 < cap_) buf_[n_++] = c;
    else ok_ = false;
}

void Writer::put(const char* s) { while (*s) putc_(*s++); }

void Writer::key(const char* k) {
    if (last_[0] && strcmp(last_, k) >= 0) sorted = false;
    strncpy(last_, k, KEY_MAX);
    last_[KEY_MAX] = 0;
    if (n_ > 1) putc_(',');
    putc_('"'); put(k); put("\":");
}

void Writer::str(const char* k, const char* v) {
    key(k);
    putc_('"');
    for (; *v; v++) putc_((*v == '"' || *v == '\\' || (uint8_t)*v < 0x20) ? '?' : *v);
    putc_('"');
}

void Writer::boolean(const char* k, bool v) { key(k); put(v ? "true" : "false"); }
void Writer::null(const char* k) { key(k); put("null"); }

void Writer::integer(const char* k, int32_t v) {
    char t[12];
    fmt_i32(t, v);
    key(k); put(t);
}

void Writer::uinteger(const char* k, uint32_t v) {
    char t[11];
    fmt_u32(t, v);
    key(k); put(t);
}

void Writer::num(const char* k, float v, uint8_t decimals) {
    if (!finite_(v)) { null(k); return; }
    char t[24];
    fmt_num(t, sizeof t, v, decimals);
    key(k);
    put(t);
    if (decimals && !strchr(t, '.') && !strchr(t, 'e')) put(".0");
}

size_t Writer::finish() {
    putc_('}');
    if (!ok_) return 0;
    uint8_t c = crc8(buf_, n_);                          // CRC of the body text {...}
    n_--;                                               // replace the closing brace by the CRC field
    put(",\"crc\":\""); putc_(HEX[c >> 4]); putc_(HEX[c & 15]); put("\"}\n");
    if (!ok_) return 0;
    buf_[n_] = 0;
    return n_;
}

// ------------------------------------------------------------------ configuration
void default_config(Config& c) {
    memset(&c, 0, sizeof c);
    // protocol.Limits (bench_params.toml) and protocol.validate constants
    c.tt_lo_deg = -110.0f; c.tt_hi_deg = 250.0f;       // [carousel] deck_range_deg
    c.tt_ms_per_45 = 1000.0f;                         // [carousel] min_s_per_45deg = 1.0 (2026-10-18, faster on the closed-loop servo)
    c.tt_slack_ms = 50.0f;                            // protocol.validate: ms < need - 50
    c.st_lo_deg = -2.0f; c.st_hi_deg = 152.0f;        // [stage] work_deg 0 / erupt_deg 150, -+2 (protocol.Limits)
    c.st_ms_min = 2000.0f;                            // protocol.Limits.st_ms_min
    c.aug_rev_max = 50.0f;                            // [auger] max_revs
    c.cpg_lo = 10.0f; c.cpg_hi = 10000.0f;            // protocol.validate CAL range
    // timing
    c.wdt_ms = 500;                                   // [mega] wdt_ms (electrical.md 7)
    c.tt_extra_ms = 2000;                             // [carousel] timeout_extra_s
    c.st_extra_ms = 2000;                             // [stage] timeout_extra_s
    c.settle_ms = 150;                                // [mega] settle_ms (assumed)
    c.aug_timeout_ms = 60000;                         // [auger] dose_timeout_s
    c.progress_ms = 200;                              // [mega] progress_ms (protocol.py: 5 Hz)
    c.estop_release_ms = 500;                         // [mega] estop_release_ms
    c.hx_timeout_min_ms = 100;                        // [mega] hx_timeout_min_ms (electrical.md 7)
    c.hx_timeout_intervals = 4;                       // [mega] hx_timeout_intervals (electrical.md 7)
    c.tare_samples = 8;                               // [mega] tare_samples
    c.hx_nominal_ms = 12.5f;                          // [scale] rate_hz = 80
    c.counts_per_g = 689.384f;                        // [scale] counts_per_g: measured 2026-10-17, 3 toonies = 21.14 g
    // M45CHW pulses ([mega] tt_/st_us_at_zero, tt_/st_us_per_deg; assumed until commissioning)
    c.tt.us_at_zero = 1134.4828f; c.tt.us_per_deg = 5.440613f;
    c.st.us_at_zero = 914.8149f; c.st.us_per_deg = 7.407407f;
    c.us_min = 500; c.us_max = 2500;                  // [mega] servo_us_min / servo_us_max
    c.home_tt_deg = 0.0f;                             // deck at its 0 deg mark
    c.home_st_deg = 0.0f;                             // [stage] work_deg
    // FB5311M-360 auger ([mega] aug_*; [auger] stall rule)
    c.aug_us_stop = 1500; c.aug_us_offset = 200;
    c.tt_release = 1;
    c.tt_closed = 1;                                  // [mega] tt_closed: FB5311M-360 on D6, feedback on A3 (2026-10-18)
    c.tt_adc_min = 2; c.tt_adc_max = 670;             // measured: one turn spans A3 2..670, wraps 668 -> 2
    c.tt_fb_sign = 1; c.tt_dir_sign = 1; c.tt_fb_zero_deg = 244.0f; // pulse above stop raises A3; zero = pick cup on the pick spot (2026-10-18)
    c.tt_us_stop = 1500; c.tt_us_db = 62;             // measured: no motion from 1460 to 1540 us; moves at 1440 / 1560
#ifdef WLB_TT_OPEN_LOOP
    c.tt_closed = 0;                                  // build flag: the old position servo (M45CHW) on D6, open loop
#endif
    c.tt_kp = 5.0f; c.tt_kd = 0.0f; c.tt_max_off = 90; c.tt_tol_deg = 2.5f; c.tt_db_deg = 1.0f; c.tt_kff = 0.0f; c.tt_hold_deg = 2.0f;                                 // [mega] tt_release: deck held by friction between moves (2026-10-17)
    c.aug_timed = 1;                                  // [mega] aug_timed: the A2 feedback wire is not fitted yet
    c.aug_rev_per_s = 0.37f;                          // [mega] aug_rev_per_s: fit 2026-10-17, turns = 0.37 * s + 0.19 (4 doses)
    c.aug_start_ms = 0;                               // [mega] aug_start_ms
    c.aug_coast_rev = 0.19f;                          // [mega] aug_coast_rev: same fit
    c.aug_dir_sign = 1; c.aug_fb_sign = 1;
    c.aug_adc_min = 0; c.aug_adc_max = 1023;
    c.stall_window_ms = 150;                          // [auger] stall_window_s
    c.stall_min_deg = 5.0f;                           // [auger] stall_min_deg
    c.max_stalls = 3;                                 // [auger] max_stalls
    c.reverse_deg = 0.0f;                             // [auger] reverse_rev = 0 (2026-10-17: anti-dribble reverse turned off on the bench)
    c.fb_max_step_deg = 45.0f;                        // [mega] aug_fb_max_step_deg
    c.fb_glitch_resync = 20;                          // [mega] aug_fb_glitch_resync
}

static float us_of(const ServoCal& s, float deg) { return s.us_at_zero + s.us_per_deg * deg; }

bool config_covers_limits(const Config& c) {
    float e[4] = {us_of(c.tt, c.tt_lo_deg), us_of(c.tt, c.tt_hi_deg), us_of(c.st, c.st_lo_deg), us_of(c.st, c.st_hi_deg)};
    for (int i = 0; i < 4; i++)
        if (!(e[i] >= c.us_min && e[i] <= c.us_max)) return false;
    return c.aug_us_stop >= c.us_min + c.aug_us_offset && c.aug_us_stop + c.aug_us_offset <= c.us_max;
}

// ------------------------------------------------------------------ core
static float smooth_(float x) {
    if (x < 0.0f) x = 0.0f;
    if (x > 1.0f) x = 1.0f;
    return x * x * (3.0f - 2.0f * x);
}

void Core::begin(const Config& cfg, uint32_t now, const Persist* restored, EmitFn emit, PersistFn persist, void* ctx) {
    cfg_ = cfg; emit_ = emit; persist_ = persist; ctx_ = ctx;
    line_n_ = 0; overflow_ = false; unsorted_ = 0;
    faults_ = 0; motion_ = M_NONE; armed_ = false; last_rx_ = now; now_ = now;
    estop_low_valid_ = false; estop_low_since_ = now; estop_in_ = false; adc_ = 0;
    tt_adc_ = 0; tt_prev_meas_ = 0.0f; tt_vel_ = 0.0f; tt_prev_t_ = now; tt_tol_since_ = now; tt_tol_on_ = false; tt_holding_ = false;
    float home[2] = {cfg.home_tt_deg, cfg.home_st_deg};
    for (int i = 0; i < 2; i++) {
        ax_[i].rest_deg = ax_[i].cur_deg = home[i];
        ax_[i].us = 0; ax_[i].known = false; ax_[i].driven = false;
    }
    if (restored) {                                     // EEPROM rest positions, only if usable
        float r[2] = {restored->tt_deg, restored->st_deg};
        bool k[2] = {restored->tt_known == 1, restored->st_known == 1};
        float lo[2] = {cfg.tt_lo_deg, cfg.st_lo_deg}, hi[2] = {cfg.tt_hi_deg, cfg.st_hi_deg};
        for (int i = 0; i < 2; i++)
            if (k[i] && finite_(r[i]) && r[i] >= lo[i] && r[i] <= hi[i]) {
                ax_[i].rest_deg = ax_[i].cur_deg = r[i];
                ax_[i].known = true;
            }
    }
    memset(&mv_, 0, sizeof mv_);
    memset(&aug_, 0, sizeof aug_);
    aug_out_ = 0;
    streaming_ = false; counts_per_g_ = cfg.counts_per_g; tared_ = false; tare_counts_ = 0;
    tare_pending_ = false; tare_seq_ = -1; tare_n_ = 0; tare_sum_ = 0;
    hx_seen_ = false; hx_last_ = now; hx_ref_ = now; hx_interval_ = cfg.hx_nominal_ms;
    emit_boot(now);
}

void Core::feed(char c, uint32_t now) {
    if (c == '\n') {
        if (overflow_) reply_err(-1, E_BADCMD, "line too long", now);
        else handle_line(line_, line_n_, now);
        line_n_ = 0;
        overflow_ = false;
        return;
    }
    if (line_n_ < IN_MAX) line_[line_n_++] = c;
    else overflow_ = true;
}

float Core::tt_measured() const {
    float span = (float)cfg_.tt_adc_max - (float)cfg_.tt_adc_min;
    float a = span > 0.0f ? ((float)tt_adc_ - (float)cfg_.tt_adc_min) / span * 360.0f : 0.0f;
    a = (float)cfg_.tt_fb_sign * a - cfg_.tt_fb_zero_deg;
    float lo = 0.5f * (cfg_.tt_lo_deg + cfg_.tt_hi_deg) - 180.0f;   // one turn centred on the deck range
    while (a < lo) a += 360.0f;
    while (a >= lo + 360.0f) a -= 360.0f;
    return a;
}

bool Core::current_deg(int i, float& deg) const {
    if (i == 0 && cfg_.tt_closed) { deg = tt_measured(); return true; }   // the feedback always knows
    if ((motion_ == M_TT && i == 0) || (motion_ == M_ST && i == 1)) { deg = ax_[i].cur_deg; return true; }
    if (ax_[i].known) { deg = ax_[i].rest_deg; return true; }
    return false;
}

float Core::deg_to_us(int i, float deg) const { return us_of(i ? cfg_.st : cfg_.tt, deg); }

static bool is_num(const Value* v) { return v && (v->type == V_INT || v->type == V_NUM); }

int Core::validate(const FlatObject& o, uint8_t& cmd, char* detail) {
    // protocol.validate, check for check and in the same order
    Sb d(detail, DETAIL_MAX);
    const Value* vs = o.get("seq");
    if (!vs || !(vs->type == V_INT || vs->type == V_BOOL)) { d.s("missing integer seq"); return E_BADCMD; }
    const Value* vc = o.get("cmd");
    static const char* const NAMES[] = {"", "PING", "TT", "ST", "AUG", "TARE", "CAL", "STREAM", "STOP", "CLR", "HB"};
    cmd = C_UNKNOWN;
    if (vc && vc->type == V_STR)
        for (uint8_t k = 1; k <= C_HB; k++)
            if (strcmp(vc->s, NAMES[k]) == 0) cmd = k;
    switch (cmd) {
    case C_PING: case C_TARE: case C_STOP: case C_CLR: case C_HB:
        return E_NONE;
    case C_STREAM: {
        const Value* on = o.get("on");
        if (!on || on->type != V_BOOL) { d.s("STREAM needs on: bool"); return E_BADCMD; }
        return E_NONE;
    }
    case C_CAL: {
        const Value* k = o.get("counts_per_g");
        if (!is_num(k) || !(k->f >= cfg_.cpg_lo && k->f <= cfg_.cpg_hi)) { d.s("counts_per_g"); return E_RANGE; }
        return E_NONE;
    }
    case C_TT: case C_ST: {
        int i = cmd == C_TT ? 0 : 1;
        const char* nm = i ? "ST" : "TT";
        const Value* vd = o.get("deg");
        const Value* vm = o.get("ms");
        if (!is_num(vd) || !is_num(vm)) { d.s(nm).s(" needs deg and ms"); return E_BADCMD; }
        float lo = i ? cfg_.st_lo_deg : cfg_.tt_lo_deg, hi = i ? cfg_.st_hi_deg : cfg_.tt_hi_deg;
        float deg = vd->f, ms = vm->f;
        if (!(lo <= deg && deg <= hi)) {
            d.s(nm).s(" deg ").f(deg, 1).s(" outside [").f(lo, 1).s(", ").f(hi, 1).s("]");
            return E_RANGE;
        }
        float us = deg_to_us(i, deg);                   // firmware-only: the pulse must be a servo pulse
        if (!(i == 0 && cfg_.tt_closed) && !(us >= cfg_.us_min && us <= cfg_.us_max)) { d.s(nm).s(" pulse ").f(us, 0).s(" us outside the servo range"); return E_RANGE; }
        if (i == 0) {
            float cur;
            float span = current_deg(0, cur) ? fabsf(deg - cur) : 0.0f;
            float need = cfg_.tt_ms_per_45 * span / 45.0f;
            if (ms < need - cfg_.tt_slack_ms) { d.s("TT ").f(span, 0).s(" deg needs >= ").f(need, 0).s(" ms"); return E_RANGE; }
        } else if (ms < cfg_.st_ms_min) {
            d.s("ST needs >= ").f(cfg_.st_ms_min, 0).s(" ms");
            return E_RANGE;
        }
        return E_NONE;
    }
    case C_AUG: {
        const Value* vr = o.get("rev");
        const Value* vd = o.get("dir");
        // Python: cmd.get('dir') not in (1, -1) -> True, 1, 1.0, -1 and -1.0 are accepted
        bool dir_ok = vd && ((vd->type == V_BOOL && vd->b) || (is_num(vd) && (vd->f == 1.0f || vd->f == -1.0f)));
        if (!is_num(vr) || !dir_ok) { d.s("AUG needs rev and dir +-1"); return E_BADCMD; }
        if (!(vr->f > 0.0f && vr->f <= cfg_.aug_rev_max)) {
            d.s("AUG rev ").f(vr->f, 2).s(" outside (0, ").f(cfg_.aug_rev_max, 0).s("]");
            return E_RANGE;
        }
        return E_NONE;
    }
    default:
        d.s("unknown command");
        if (vc && vc->type == V_STR) d.s(" '").s(vc->s).s("'");
        return E_BADCMD;
    }
}

void Core::handle_line(const char* line, size_t n, uint32_t now) {
    now_ = now;
    char detail[DETAIL_MAX];
    detail[0] = 0;
    int e = decode_line(line, n, obj_, detail, sizeof detail);
    if (e) { reply_err(-1, e, detail, now); return; }
    last_rx_ = now;
    armed_ = true;
    const Value* vs = obj_.get("seq");
    int32_t seq = (vs && (vs->type == V_INT || vs->type == V_BOOL)) ? vs->i : -1;
    uint8_t cmd = C_UNKNOWN;
    e = validate(obj_, cmd, detail);
    if (e) { reply_err(seq, e, detail, now); return; }

    // order of checks follows SimMega.handle
    if (cmd == C_HB) return;
    if (cmd == C_PING) { reply_ping(seq, now); return; }
    if (cmd == C_STOP) {                                // always accepted: auger off, servos hold where they are
        if (motion_ == M_AUG) aug_out_ = 0;
        if (motion_ == M_TT || motion_ == M_ST) {
            Axis& x = ax_[motion_ == M_ST];
            x.rest_deg = x.cur_deg;
            x.known = true;
            motion_ = M_NONE;
            save();
        }
        motion_ = M_NONE;
        reply_simple(seq, "ok", now);
        return;
    }
    if (cmd == C_CLR) {
        if ((faults_ & F_ESTOP) && !estop_released(now)) { reply_err(seq, E_STATE, "e-stop still pressed", now); return; }
        const Value* h = obj_.get("home");
        bool home = h && h->type == V_BOOL && h->b;
        if (home && motion_ != M_NONE) { reply_err(seq, E_STATE, "CLR home while moving", now); return; }
        faults_ = 0;
        hx_ref_ = now;                                  // a fresh HX711 timeout window after clearing
        if (home) {                                     // operator: deck at 0 deg and stage at WORK, by hand
            float hd[2] = {cfg_.home_tt_deg, cfg_.home_st_deg};
            for (int i = 0; i < 2; i++)
                if (!ax_[i].driven) { ax_[i].rest_deg = ax_[i].cur_deg = hd[i]; ax_[i].known = true; }
            save();
        }
        reply_simple(seq, "ok", now);
        return;
    }
    // Scale commands move nothing, so they stay available while the e-stop is latched (bring-up, weighing).
    if (cmd == C_STREAM) {
        streaming_ = obj_.get("on")->b;
        hx_ref_ = now;
        reply_simple(seq, "ok", now);
        return;
    }
    if (cmd == C_TARE) {                                // mean of the next tare_samples conversions, then reply
        if (faults_ & F_HX_TIMEOUT) { reply_err(seq, E_STATE, "HX711 fault", now); return; }
        if (tare_pending_) { reply_err(seq, E_STATE, "tare pending", now); return; }
        tare_pending_ = true; tare_seq_ = seq; tare_n_ = 0; tare_sum_ = 0; hx_ref_ = now;
        return;
    }
    if (cmd == C_CAL) { counts_per_g_ = obj_.get("counts_per_g")->f; reply_simple(seq, "ok", now); return; }
    if (faults_ & F_ESTOP) { reply_err(seq, E_ESTOP, "latched", now); return; }
    if (faults_) {
        Sb d(detail, sizeof detail);
        d.s("faults latched:");
        for (uint8_t i = 0; i < 8; i++)
            if (faults_ & (1u << i)) d.s(" ").s(FAULT_NAMES[i]);
        reply_err(seq, E_STATE, detail, now);
        return;
    }
    if (motion_ != M_NONE) {
        static const char* const MN[] = {"", "TT", "ST", "AUG"};
        Sb(detail, sizeof detail).s(MN[motion_]).s(" running");
        reply_err(seq, E_BUSY, detail, now);
        return;
    }
    if (cmd == C_TT || cmd == C_ST) {
        int i = cmd == C_ST;
        if (!ax_[i].known && !(i == 0 && cfg_.tt_closed)) { reply_err(seq, E_STATE, "position unknown: home it by hand, then CLR home:true", now); return; }   // closed-loop TT: measured, never unknown
        start_axis(i, seq, obj_.get("deg")->f, obj_.get("ms")->f, now);
        reply_simple(seq, "ack", now);
        return;
    }
    const Value* vd = obj_.get("dir");                  // C_AUG
    start_auger(seq, obj_.get("rev")->f, (vd->type == V_BOOL || vd->f > 0.0f) ? 1 : -1, now);
    reply_simple(seq, "ack", now);
}

void Core::start_axis(int i, int32_t seq, float deg, float ms, uint32_t now) {
    Axis& x = ax_[i];
    mv_.seq = seq;
    mv_.t0 = now;
    mv_.dur_ms = ms > 0.0f ? ms : 0.0f;
    mv_.timeout_ms = ms + (float)(i ? cfg_.st_extra_ms : cfg_.tt_extra_ms);
    mv_.deg0 = x.rest_deg;
    mv_.deg1 = deg;
    mv_.us0 = deg_to_us(i, x.rest_deg);
    mv_.us1 = deg_to_us(i, deg);
    x.cur_deg = x.rest_deg;
    x.us = mv_.us0;                                     // the first pulse is the rest position: no snap
    if (i == 0 && cfg_.tt_closed) {
        mv_.deg0 = x.cur_deg = tt_measured();
        x.us = (float)cfg_.tt_us_stop;
        tt_prev_meas_ = mv_.deg0; tt_prev_t_ = now; tt_vel_ = 0.0f; tt_tol_on_ = false;
    }
    x.driven = true;
    x.known = false;                                    // persisted: a reset during the move boots unknown
    motion_ = i ? M_ST : M_TT;
    save();
}

void Core::tt_meas_update(uint32_t now, float meas) {
    uint32_t dt = (uint32_t)(now - tt_prev_t_);
    if (dt >= 20) {                                     // speed estimate every >= 20 ms, low-passed
        float dm = meas - tt_prev_meas_;
        if (dm > 180.0f) dm -= 360.0f; else if (dm < -180.0f) dm += 360.0f;
        tt_vel_ += 0.4f * (dm * 1000.0f / (float)dt - tt_vel_);
        tt_prev_meas_ = meas; tt_prev_t_ = now;
    }
}

float Core::tt_pulse(float u) const {                   // u in us past the deadband (signed), limited
    float lim = (float)cfg_.tt_max_off;
    if (u > lim) u = lim; else if (u < -lim) u = -lim;
    float off = u > 0.0f ? (float)cfg_.tt_us_db + u : (u < 0.0f ? -(float)cfg_.tt_us_db + u : 0.0f);
    return (float)cfg_.tt_us_stop + (float)cfg_.tt_dir_sign * off;
}

// Move: the target follows the smooth profile (slow start, slow stop); feedforward drives at the profile's speed,
// P corrects the position lag, D the speed error. Done once inside tt_tol_deg for settle_ms.
void Core::tt_closed_tick(uint32_t now, float el, float s) {
    Axis& x = ax_[0];
    float span = mv_.deg1 - mv_.deg0;
    float target = mv_.deg0 + span * s;
    float xr = mv_.dur_ms > 0.0f ? el / mv_.dur_ms : 1.0f;
    float vref = (xr > 0.0f && xr < 1.0f) ? span * 6.0f * xr * (1.0f - xr) * 1000.0f / mv_.dur_ms : 0.0f;
    float meas = tt_measured();
    tt_meas_update(now, meas);
    float err = target - meas;
    bool profile_done = el >= mv_.dur_ms;
    float u = cfg_.tt_kff * vref + cfg_.tt_kp * err + cfg_.tt_kd * (vref - tt_vel_);
    if (profile_done && fabsf(err) < cfg_.tt_db_deg) u = 0.0f;
    x.us = tt_pulse(u);
    x.cur_deg = meas;
    if (profile_done && fabsf(mv_.deg1 - meas) <= cfg_.tt_tol_deg) {
        if (!tt_tol_on_) { tt_tol_on_ = true; tt_tol_since_ = now; }
        if ((uint32_t)(now - tt_tol_since_) >= cfg_.settle_ms) {
            x.rest_deg = mv_.deg1; x.known = true;      // keep driving: tt_hold_tick holds the target from here
            tt_holding_ = false;
            motion_ = M_NONE;
            save();
            Writer w;
            w.begin(out_, OUT_MAX);
            w.str("cmd", "TT"); w.num("deg", meas, 2); w.boolean("done", true);
            w.integer("seq", mv_.seq); w.uinteger("t", now);
            send(w);
        }
    } else tt_tol_on_ = false;
}

// Between moves: stop pulse inside the band; past tt_hold_deg, P(D) back to rest until inside tt_db_deg again.
void Core::tt_hold_tick(uint32_t now) {
    Axis& x = ax_[0];
    float meas = tt_measured();
    tt_meas_update(now, meas);
    x.cur_deg = meas;
    float err = x.rest_deg - meas;
    if (!tt_holding_ && fabsf(err) > cfg_.tt_hold_deg) tt_holding_ = true;
    if (tt_holding_ && fabsf(err) < cfg_.tt_db_deg) tt_holding_ = false;
    x.us = tt_holding_ ? tt_pulse(cfg_.tt_kp * err - cfg_.tt_kd * tt_vel_) : (float)cfg_.tt_us_stop;
}

void Core::axis_tick(uint32_t now) {
    int i = motion_ == M_ST;
    Axis& x = ax_[i];
    float el = (float)(uint32_t)(now - mv_.t0);
    if (el > mv_.timeout_ms) { fault(i ? F_ST_TIMEOUT : F_TT_TIMEOUT, now); return; }
    float s = mv_.dur_ms > 0.0f ? smooth_(el / mv_.dur_ms) : 1.0f;
    if (i == 0 && cfg_.tt_closed) { tt_closed_tick(now, el, s); return; }
    x.us = mv_.us0 + (mv_.us1 - mv_.us0) * s;
    x.cur_deg = mv_.deg0 + (mv_.deg1 - mv_.deg0) * s;
    if (el >= mv_.dur_ms + (float)cfg_.settle_ms) {    // open loop: done once the profile ended and settled
        x.rest_deg = x.cur_deg = mv_.deg1;
        x.us = mv_.us1;
        x.known = true;
        if (i == 0 && cfg_.tt_release) x.driven = false;   // limp between moves; the next move starts from rest_deg
        motion_ = M_NONE;
        save();
        Writer w;
        w.begin(out_, OUT_MAX);
        w.str("cmd", i ? "ST" : "TT"); w.num("deg", mv_.deg1, 2); w.boolean("done", true);
        w.integer("seq", mv_.seq); w.uinteger("t", now);
        send(w);
    }
}

void Core::start_auger(int32_t seq, float rev, int8_t dir, uint32_t now) {
    memset(&aug_, 0, sizeof aug_);
    aug_.seq = seq;
    aug_.t0 = aug_.win_t0 = aug_.next_prog = aug_.last_t = now;
    if (cfg_.aug_timed) aug_.net = aug_.hw = cfg_.aug_coast_rev * 360.0f;   // it coasts this far after the stop
    aug_.target = rev * 360.0f;
    aug_.dir = dir;
    aug_.phase = A_DOSE;
    aug_.fb_init = false;
    motion_ = M_AUG;
    aug_out_ = (uint16_t)(cfg_.aug_us_stop + dir * cfg_.aug_dir_sign * (int16_t)cfg_.aug_us_offset);
}

float Core::fb_angle(uint16_t adc) const {
    float span = (float)cfg_.aug_adc_max - (float)cfg_.aug_adc_min;
    if (span <= 0.0f) return 0.0f;
    return ((float)adc - (float)cfg_.aug_adc_min) / span * 360.0f;
}

void Core::begin_reverse(uint32_t now, uint8_t after) {
    aug_.phase = A_REVERSE;
    aug_.after = after;
    aug_.rev_until = aug_.net - cfg_.reverse_deg;
    aug_.win_t0 = now;
    aug_.win_net = aug_.net;
}

void Core::auger_tick(uint32_t now, uint16_t adc) {
    // Revolutions by unwrapping the A2 feedback angle. Stall rule (electrical.md 6): while commanded, less than
    // stall_min_deg of progress in stall_window_ms -> stop, reverse reverse_deg, retry; max_stalls -> AUGER_JAM.
    // The rule is applied in both directions (the simulator checks the forward direction only).
    Auger& a = aug_;
    if ((uint32_t)(now - a.t0) > cfg_.aug_timeout_ms) { fault(F_AUG_TIMEOUT, now); return; }
    if (cfg_.aug_timed) {
        // No feedback wire: progress is the measured speed times the time the output has been driving, forward while
        // dosing and backward while reversing. Everything below (dose target, 1/4-turn reverse, done) is unchanged;
        // the stall rule is off because there is nothing to detect a jam with.
        uint32_t from = a.last_t;
        if (a.phase == A_DOSE && (uint32_t)(from - a.t0) < cfg_.aug_start_ms) from = a.t0 + cfg_.aug_start_ms;   // spin-up
        float dt = (int32_t)(now - from) > 0 ? (float)(uint32_t)(now - from) / 1000.0f : 0.0f;
        a.last_t = now;
        a.net += cfg_.aug_rev_per_s * 360.0f * dt * (a.phase == A_DOSE ? 1.0f : -1.0f);
    } else {
        float ang = fb_angle(adc);
        if (!a.fb_init) { a.last_fb = ang; a.fb_init = true; }
        float d = ang - a.last_fb;
        if (d > 180.0f) d -= 360.0f;
        else if (d < -180.0f) d += 360.0f;
        if (fabsf(d) <= cfg_.fb_max_step_deg) {
            a.net += d * (float)(cfg_.aug_fb_sign * cfg_.aug_dir_sign * a.dir);   // progress in the commanded sense
            a.last_fb = ang;
            a.glitches = 0;
        } else if (++a.glitches >= cfg_.fb_glitch_resync) {
            a.last_fb = ang;                                // persistent jump: resynchronise, motion not counted
            a.glitches = 0;
        }
    }
    if (a.phase == A_DOSE) {
        if (a.net > a.hw) a.hw = a.net;                 // dosed revolutions = high-water mark of net progress
        if ((int32_t)(now - a.next_prog) >= 0) {
            Writer w;
            w.begin(out_, OUT_MAX);
            w.num("aug", a.hw / 360.0f, 3); w.integer("seq", a.seq); w.uinteger("t", now);
            send(w);
            a.next_prog = now + cfg_.progress_ms;
        }
        if (a.hw >= a.target) begin_reverse(now, A_FINISH);   // reverse 1/4 turn against dribble
    } else if (a.phase == A_REVERSE && a.net <= a.rev_until) {
        a.phase = a.after;
        a.win_t0 = now;
        a.win_net = a.net;
    }
    if (!cfg_.aug_timed && a.phase != A_FINISH && (uint32_t)(now - a.win_t0) >= cfg_.stall_window_ms) {
        if (fabsf(a.net - a.win_net) < cfg_.stall_min_deg) {
            a.stalls++;
            if (a.stalls >= cfg_.max_stalls) { fault(F_AUGER_JAM, now); return; }
            if (a.phase == A_DOSE) begin_reverse(now, A_DOSE);
            else a.phase = a.hw >= a.target ? A_FINISH : A_DOSE;
        }
        a.win_t0 = now;
        a.win_net = a.net;
    }
    if (a.phase == A_FINISH) {
        aug_out_ = 0;
        motion_ = M_NONE;
        Writer w;
        w.begin(out_, OUT_MAX);
        w.str("cmd", "AUG"); w.boolean("done", true); w.num("rev", a.hw / 360.0f, 3);
        w.integer("seq", a.seq); w.integer("stalls", a.stalls); w.uinteger("t", now);
        send(w);
        return;
    }
    int fwd = a.dir * cfg_.aug_dir_sign * (a.phase == A_DOSE ? 1 : -1);
    aug_out_ = (uint16_t)(cfg_.aug_us_stop + fwd * (int)cfg_.aug_us_offset);
}

void Core::hx_sample(int32_t raw, uint32_t now) {
    if (hx_seen_) {
        float dt = (float)(uint32_t)(now - hx_last_);
        if (dt > 0.0f && dt < 1000.0f) hx_interval_ += 0.1f * (dt - hx_interval_);   // measured ready interval
    }
    hx_seen_ = true;
    hx_last_ = hx_ref_ = now;
    if (tare_pending_) {
        tare_sum_ += raw;
        if (++tare_n_ >= cfg_.tare_samples) {
            int64_t n = tare_n_;
            tare_counts_ = (int32_t)(tare_sum_ >= 0 ? (tare_sum_ + n / 2) / n : (tare_sum_ - n / 2) / n);
            tared_ = true;
            tare_pending_ = false;
            Writer w;
            w.begin(out_, OUT_MAX);
            w.boolean("ok", true); w.integer("seq", tare_seq_); w.uinteger("t", now); w.integer("tare", tare_counts_);
            send(w);
        }
    }
    if (streaming_) {
        Writer w;
        w.begin(out_, OUT_MAX);
        w.integer("raw", raw); w.uinteger("t", now);
        w.num("w", (float)(raw - (tared_ ? tare_counts_ : 0)) / counts_per_g_, 3);
        send(w);
    }
}

uint32_t Core::hx_timeout_ms() const {
    float t = (float)cfg_.hx_timeout_intervals * hx_interval_;
    return t > (float)cfg_.hx_timeout_min_ms ? (uint32_t)t : cfg_.hx_timeout_min_ms;
}

bool Core::estop_released(uint32_t now) const {
    return estop_low_valid_ && (uint32_t)(now - estop_low_since_) >= cfg_.estop_release_ms;
}

void Core::tick(uint32_t now, bool estop_open, uint16_t aug_adc) {
    now_ = now;
    estop_in_ = estop_open;
    adc_ = aug_adc;
    if (estop_open) {
        estop_low_valid_ = false;
        if (!(faults_ & F_ESTOP)) fault(F_ESTOP, now);
    } else if (!estop_low_valid_) {
        estop_low_valid_ = true;
        estop_low_since_ = now;
    }
    if (armed_ && motion_ != M_NONE && (uint32_t)(now - last_rx_) > cfg_.wdt_ms) fault(F_WDT, now);
    if ((streaming_ || tare_pending_) && !(faults_ & F_HX_TIMEOUT) && (uint32_t)(now - hx_ref_) > hx_timeout_ms())
        fault(F_HX_TIMEOUT, now);
    if (motion_ == M_TT || motion_ == M_ST) axis_tick(now);
    if (cfg_.tt_closed && motion_ != M_TT && ax_[0].driven && ax_[0].known && !faults_) tt_hold_tick(now);
    else if (motion_ == M_AUG) auger_tick(now, aug_adc);
    if (estop_open) all_off();                          // the D2 interrupt has already cut the PWM
}

void Core::fault(uint16_t f, uint32_t now) {
    if (faults_ & f) return;
    faults_ |= f;
    Writer w;
    w.begin(out_, OUT_MAX);
    if (f == F_WDT) {
        if (motion_ == M_AUG) w.num("aug", aug_.hw / 360.0f, 3);
        else w.null("aug");
    }
    w.str("fault", fault_name(f));
    if (f == F_AUGER_JAM) w.num("rev", aug_.hw / 360.0f, 3);
    if (f == F_AUGER_JAM || f == F_AUG_TIMEOUT) w.integer("seq", aug_.seq);
    if (f == F_TT_TIMEOUT || f == F_ST_TIMEOUT) w.integer("seq", mv_.seq);
    w.uinteger("t", now);
    send(w);
    if (motion_ == M_AUG) { motion_ = M_NONE; aug_out_ = 0; }   // every fault stops the auger
    if (f == F_ESTOP || f == F_WDT || f == F_TT_TIMEOUT || f == F_ST_TIMEOUT || f == F_AUG_TIMEOUT) {
        if (motion_ == M_TT || motion_ == M_ST) { motion_ = M_NONE; save(); }   // interrupted: axis stays unknown
        all_off();                                      // all PWM off: servos limp
    }
    if (f == F_HX_TIMEOUT && tare_pending_) {
        tare_pending_ = false;
        reply_err(tare_seq_, E_STATE, "HX711 timeout", now);
    }
}

void Core::all_off() {
    ax_[0].driven = ax_[1].driven = false;
    aug_out_ = 0;
}

void Core::save() {
    if (!persist_) return;
    Persist p;
    p.tt_deg = ax_[0].rest_deg; p.st_deg = ax_[1].rest_deg;
    p.tt_known = ax_[0].known ? 1 : 0; p.st_known = ax_[1].known ? 1 : 0;
    persist_(ctx_, p);
}

void Core::send(Writer& w) {
    size_t n = w.finish();
    if (!w.sorted) unsorted_++;
    if (n && emit_) emit_(ctx_, out_, n);
}

void Core::reply_err(int32_t seq, int code, const char* detail, uint32_t now) {
    Writer w;
    w.begin(out_, OUT_MAX);
    w.str("detail", detail); w.str("err", err_name(code)); w.integer("seq", seq); w.uinteger("t", now);
    send(w);
}

void Core::reply_simple(int32_t seq, const char* key, uint32_t now) {
    Writer w;
    w.begin(out_, OUT_MAX);
    w.boolean(key, true); w.integer("seq", seq); w.uinteger("t", now);
    send(w);
}

void Core::reply_ping(int32_t seq, uint32_t now) {
    float tt, st;
    bool ktt = current_deg(0, tt), kst = current_deg(1, st);
    Writer w;
    w.begin(out_, OUT_MAX);
    w.integer("adc", adc_); w.boolean("estop", estop_in_); w.integer("faults", faults_); w.str("fw", WLB_FW_ID);
    w.num("hx_ms", hx_interval_, 2); w.boolean("ok", true); w.str("pos", ktt && kst ? "known" : "unknown");
    w.integer("seq", seq); w.boolean("sim", false);
    if (kst) w.num("st", st, 2); else w.null("st");
    w.uinteger("t", now);
    if (ktt) w.num("tt", tt, 2); else w.null("tt");
    if (cfg_.tt_closed) w.integer("tt_adc", tt_adc_);   // firmware-only: raw A3, for calibrating the feedback
    send(w);
}

void Core::emit_boot(uint32_t now) {
    Writer w;
    w.begin(out_, OUT_MAX);
    w.boolean("boot", true); w.boolean("cal_ok", config_covers_limits(cfg_)); w.str("fw", WLB_FW_ID);
    w.str("pos", ax_[0].known && ax_[1].known ? "known" : "unknown");
    if (ax_[1].known) w.num("st", ax_[1].rest_deg, 2); else w.null("st");
    w.uinteger("t", now);
    if (ax_[0].known) w.num("tt", ax_[0].rest_deg, 2); else w.null("tt");
    send(w);
}

}  // namespace wlb
