// Host test for the Mega firmware core (firmware/mega/wlb_mega/protocol_core.cpp). No Arduino, no hardware.
//
//   test_protocol_core                  built-in checks only
//   test_protocol_core SCRIPT|-         built-in checks, then a script (tests/test_firmware_core.py writes it
//                                       from benchsim.protocol.encode lines; see benchsim.backends.real)
//   test_protocol_core --dump-config    the compiled-in defaults, one "CFG name value" per line
//   test_protocol_core --live           real-time loop on stdin/stdout with a plant model (serial loopback)
//
// The core runs against a plant model: the auger turns at 360/rev_s deg/s when its pulse is off the stop
// centre (unless jammed) and its A2 feedback is the angle mod 360 over the ADC range; the HX711 delivers a
// conversion every 12.5 ms with Gaussian-ish noise. Every emitted line is printed as "OUT <line>" so the
// Python side can decode it with benchsim.protocol.decode. The last line is "SUMMARY pass=N fail=M".
//
// Script commands (one per line; "fw " prefix = firmware only, "sim " prefix = skipped here):
//   reset [known|unknown] [tt=D] [st=D]   fresh core, plant, records       cfg NAME VALUE / cfgclear
//   send LINE | long N                     feed LINE + '\n' / N 'x' + '\n'  run MS
//   estop 0|1   jam 0|1|2   hx 0|1   grams G   glitch MS DEG   mark
//   expect SEQ ack|ok|none|err:CODE        expect_done SEQ 0|1              expect_fault CODE 0|1
//   expect_samples MIN MAX                 expect_progress SEQ MIN          expect_num SEQ KEY MIN MAX
//   expect_out tt|st|aug on|off            expect_known tt|st 0|1           crc HEX TEXT
//   expect_persist tt|st KNOWN DEG         expect_plant_deg MIN MAX
//   v SEQ KIND LINE                        validation vector: reset, send, run 200 ms, first reply == KIND
#include "../wlb_mega/protocol_core.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <fstream>
#include <iostream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#ifndef _WIN32
#include <sys/select.h>
#include <sys/time.h>
#include <unistd.h>
#endif

using namespace wlb;

static int g_pass = 0, g_fail = 0;
static bool g_verbose = false;

static void check(bool ok, const std::string& what) {
    if (ok) {
        g_pass++;
        if (g_verbose) printf("PASS %s\n", what.c_str());
    } else {
        g_fail++;
        printf("FAIL %s\n", what.c_str());
    }
}

// ------------------------------------------------------------------ plant
struct Plant {
    double aug_deg = 0.0, aug_rate = 300.0;             // deg/s: 360 / [auger] rev_s (script: cfg plant_rev_s)
    int jam = 0;                                        // 1: blocked above the stop centre, 2: blocked both ways
    bool hx_on = true, estop = false;
    double next_hx = 12.5, hx_period = 12.5;            // [scale] rate_hz 80
    double grams = 0.0, cpg = 420.0, noise_g = 0.07;    // [scale] counts_per_g, noise_g
    int32_t offset = 41237;                             // arbitrary HX711 zero, as SimMega
    uint32_t rng = 12345;
    uint32_t glitch_until = 0;
    double glitch_deg = 170.0;

    double gauss() {                                    // sum of 4 uniforms, unit variance
        double s = 0;
        for (int i = 0; i < 4; i++) { rng = rng * 1664525u + 1013904223u; s += (rng >> 8) / 16777216.0 - 0.5; }
        return s * sqrt(3.0);
    }
    uint16_t adc(const Config& c, uint32_t now) const {
        double a = fmod(aug_deg, 360.0);
        if (a < 0) a += 360.0;
        if (now < glitch_until) a = fmod(a + glitch_deg + 360.0, 360.0);   // feedback glitch: the reading jumps
        double v = c.aug_adc_min + a / 360.0 * (c.aug_adc_max - c.aug_adc_min);
        return (uint16_t)(v + 0.5);
    }
    void step(const Config& c, uint16_t aug_us, double dt_ms) {
        if (!aug_us) return;
        int d = (int)aug_us - (int)c.aug_us_stop;
        if (d > -30 && d < 30) return;                  // servo dead band around the stop pulse
        int s = (d > 0 ? 1 : -1) * c.aug_fb_sign;
        if (jam == 2 || (jam == 1 && d > 0)) return;
        aug_deg += s * aug_rate * dt_ms / 1000.0;
    }
};

// ------------------------------------------------------------------ records of what the core sent
// Replies are read with this unbounded reader, not the core's command parser (whose key and string limits are
// sized for commands). The CRC is checked independently of decode_line.
struct Tok {
    char type = 'z';            // s string, n number, b bool, z null
    std::string s;
    double num = 0.0;
    bool b = false;
};

struct Msg {
    std::map<std::string, Tok> o;
    std::string line;
    const Tok* get(const char* k) const {
        std::map<std::string, Tok>::const_iterator it = o.find(k);
        return it == o.end() ? 0 : &it->second;
    }
};

static bool read_reply(const std::string& line, Msg& m, std::string& why) {
    std::string L = line;
    while (!L.empty() && (L[L.size() - 1] == '\n' || L[L.size() - 1] == '\r')) L.erase(L.size() - 1);
    const std::string tail = ",\"crc\":\"";
    if (L.size() < 12 || L.compare(L.size() - 12, 8, tail) != 0 || L.compare(L.size() - 2, 2, "\"}") != 0) { why = "no CRC field"; return false; }
    std::string body = L.substr(0, L.size() - 12) + "}";
    char want[3];
    snprintf(want, sizeof want, "%02x", crc8(body.data(), body.size()));
    if (L.compare(L.size() - 4, 2, want) != 0) { why = "CRC mismatch"; return false; }
    size_t i = 0;
    if (body[i++] != '{') { why = "not an object"; return false; }
    while (i < body.size() && body[i] != '}') {
        if (body[i] != '"') { why = "expected key"; return false; }
        size_t j = body.find('"', i + 1);
        std::string key = body.substr(i + 1, j - i - 1);
        i = j + 1;
        if (body[i++] != ':') { why = "expected :"; return false; }
        Tok t;
        if (body[i] == '"') {
            size_t e = i + 1;
            while (e < body.size() && body[e] != '"') e += body[e] == '\\' ? 2 : 1;
            t.type = 's'; t.s = body.substr(i + 1, e - i - 1); i = e + 1;
        } else {
            size_t e = body.find_first_of(",}", i);
            std::string v = body.substr(i, e - i);
            if (v == "true" || v == "false") { t.type = 'b'; t.b = v == "true"; }
            else if (v == "null") t.type = 'z';
            else { t.type = 'n'; char* end = 0; t.num = strtod(v.c_str(), &end); if (!end || *end) { why = "bad number " + v; return false; } }
            i = e;
        }
        m.o[key] = t;
        if (body[i] == ',') i++;
    }
    return true;
}

struct Rig {
    Core core;
    Config cfg;
    Plant plant;
    uint32_t now = 0;
    std::vector<Msg> out;
    std::map<int32_t, std::vector<size_t> > by_seq;     // replies (and done) per seq
    std::map<int32_t, int> progress;
    std::vector<std::string> faults;
    int samples = 0, bad_lines = 0;
    Persist persisted;
    int persist_calls = 0;
    bool print_out = true;

    static void on_emit(void* ctx, const char* line, size_t n) { ((Rig*)ctx)->record(std::string(line, n)); }
    static void on_persist(void* ctx, const Persist& p) {
        Rig* r = (Rig*)ctx;
        r->persisted = p;
        r->persist_calls++;
    }

    void record(const std::string& line) {
        if (print_out) printf("OUT %s", line.c_str());
        Msg m;
        m.line = line;
        std::string why;
        if (!read_reply(line, m, why)) {
            bad_lines++;
            check(false, "output line reads back: " + line + " (" + why + ")");
            return;
        }
        out.push_back(m);
        const Tok* seq = m.get("seq");
        // classification order of interfaces.MegaClient._pump
        if (m.get("w")) samples++;
        else if (m.get("fault")) faults.push_back(m.get("fault")->s);
        else if (m.get("aug")) progress[seq ? (int32_t)seq->num : -1]++;
        else if (seq) by_seq[(int32_t)seq->num].push_back(out.size() - 1);
    }

    void reset(bool known, float tt, float st, const Config& c) {
        cfg = c;
        plant = Plant();
        plant.cpg = c.counts_per_g;
        out.clear(); by_seq.clear(); progress.clear(); faults.clear();
        samples = 0;
        persist_calls = 0;
        Persist p;
        p.tt_deg = tt; p.st_deg = st; p.tt_known = known; p.st_known = known;
        now = 1000;
        plant.next_hx = now + plant.hx_period;
        core.begin(cfg, now, known ? &p : 0, on_emit, on_persist, this);
    }

    void feed(const std::string& s) {
        for (size_t i = 0; i < s.size(); i++) core.feed(s[i], now);
        core.feed('\n', now);
    }

    void run(uint32_t ms) {
        for (uint32_t k = 0; k < ms; k++) {
            now++;
            plant.step(cfg, core.aug_us(), 1.0);
            if (plant.hx_on && now >= plant.next_hx) {
                plant.next_hx += plant.hx_period;
                double g = plant.grams + plant.noise_g * plant.gauss();
                core.hx_sample((int32_t)lround(plant.offset + g * plant.cpg), now);
            }
            core.tick(now, plant.estop, plant.adc(cfg, now));
            invariants();
        }
    }

    void invariants() {
        // safety rules checked on every tick; only failures are counted so the summary stays readable
        uint16_t t = core.tt_us(), s = core.st_us(), a = core.aug_us();
        if (plant.estop && (t || s || a)) check(false, "e-stop open but an output is on");
        if (core.motion() != Core::M_AUG && a) check(false, "auger output on outside AUG");
        if ((t && (t < cfg.us_min || t > cfg.us_max)) || (s && (s < cfg.us_min || s > cfg.us_max)))
            check(false, "servo pulse outside [us_min, us_max]");
        if (a && (a < cfg.aug_us_stop - cfg.aug_us_offset || a > cfg.aug_us_stop + cfg.aug_us_offset))
            check(false, "auger pulse outside stop +- offset");
        if (core.unsorted_lines()) check(false, "an output line had unsorted keys");
    }

    const Msg* first_reply(int32_t seq) const {
        std::map<int32_t, std::vector<size_t> >::const_iterator it = by_seq.find(seq);
        return it == by_seq.end() || it->second.empty() ? 0 : &out[it->second[0]];
    }

    std::string kind(const Msg* m) const {
        if (!m) return "none";
        if (m->get("ack")) return "ack";
        if (m->get("ok")) return "ok";
        if (m->get("done")) return "done";
        if (m->get("err")) return std::string("err:") + m->get("err")->s;
        return "?";
    }

    bool has_done(int32_t seq) const {
        std::map<int32_t, std::vector<size_t> >::const_iterator it = by_seq.find(seq);
        if (it == by_seq.end()) return false;
        for (size_t i = 0; i < it->second.size(); i++)
            if (out[it->second[i]].get("done")) return true;
        return false;
    }

    const Tok* last_value(int32_t seq, const char* key) const {
        std::map<int32_t, std::vector<size_t> >::const_iterator it = by_seq.find(seq);
        if (it == by_seq.end()) return 0;
        const Tok* v = 0;
        for (size_t i = 0; i < it->second.size(); i++)
            if (out[it->second[i]].get(key)) v = out[it->second[i]].get(key);
        return v;
    }
};

// ------------------------------------------------------------------ config access by name
struct Field {
    const char* name;
    char kind;                  // f float, u uint32, b uint8, h uint16, c int8
    size_t off;
};

#define F(k, m) {#m, k, offsetof(Config, m)}
static const Field FIELDS[] = {
    F('f', tt_lo_deg), F('f', tt_hi_deg), F('f', tt_ms_per_45), F('f', tt_slack_ms), F('f', st_lo_deg), F('f', st_hi_deg),
    F('f', st_ms_min), F('f', aug_rev_max), F('f', cpg_lo), F('f', cpg_hi), F('u', wdt_ms), F('u', tt_extra_ms),
    F('u', st_extra_ms), F('u', settle_ms), F('u', aug_timeout_ms), F('u', progress_ms), F('u', estop_release_ms),
    F('u', hx_timeout_min_ms), F('b', hx_timeout_intervals), F('b', tare_samples), F('f', hx_nominal_ms),
    F('f', counts_per_g), F('f', tt.us_at_zero), F('f', tt.us_per_deg), F('f', st.us_at_zero), F('f', st.us_per_deg),
    F('h', us_min), F('h', us_max), F('f', home_tt_deg), F('f', home_st_deg), F('h', aug_us_stop), F('h', aug_us_offset),
    F('c', aug_dir_sign), F('c', aug_fb_sign), F('h', aug_adc_min), F('h', aug_adc_max), F('u', stall_window_ms),
    F('f', stall_min_deg), F('b', max_stalls), F('f', reverse_deg), F('f', fb_max_step_deg), F('b', fb_glitch_resync), F('b', aug_timed), F('f', aug_rev_per_s), F('u', aug_start_ms), F('f', aug_coast_rev), F('b', tt_release),
};
#undef F

static double get_field(const Config& c, const Field& f) {
    const char* p = (const char*)&c + f.off;
    switch (f.kind) {
    case 'f': return *(const float*)p;
    case 'u': return *(const uint32_t*)p;
    case 'b': return *(const uint8_t*)p;
    case 'h': return *(const uint16_t*)p;
    default: return *(const int8_t*)p;
    }
}

static bool set_field(Config& c, const std::string& name, double v) {
    for (size_t i = 0; i < sizeof FIELDS / sizeof FIELDS[0]; i++) {
        if (name != FIELDS[i].name) continue;
        char* p = (char*)&c + FIELDS[i].off;
        switch (FIELDS[i].kind) {
        case 'f': *(float*)p = (float)v; break;
        case 'u': *(uint32_t*)p = (uint32_t)v; break;
        case 'b': *(uint8_t*)p = (uint8_t)v; break;
        case 'h': *(uint16_t*)p = (uint16_t)v; break;
        default: *(int8_t*)p = (int8_t)v; break;
        }
        return true;
    }
    return false;
}

// ------------------------------------------------------------------ built-in checks (no Python needed)
static bool parses(const char* s, FlatObject& o) {
    const char* err = 0;
    return parse_flat_json(s, strlen(s), o, &err);
}

static void builtin_checks() {
    check(crc8("123456789", 9) == 0xF4, "crc8 check value 0xF4 (CRC-8/ATM)");
    Config c;
    default_config(c);
    check(config_covers_limits(c), "default pulse calibration covers the protocol degree limits");

    char b[32];
    fmt_num(b, sizeof b, 1.5f, 3); check(strcmp(b, "1.5") == 0, std::string("fmt 1.5 -> ") + b);
    fmt_num(b, sizeof b, 90.0f, 2); check(strcmp(b, "90.0") == 0, std::string("fmt 90 -> ") + b);
    fmt_num(b, sizeof b, -0.0004f, 3); check(strcmp(b, "0.0") == 0, std::string("fmt -0.0004 -> ") + b);
    fmt_num(b, sizeof b, -12.3456f, 2); check(strcmp(b, "-12.35") == 0, std::string("fmt -12.3456 -> ") + b);
    fmt_num(b, sizeof b, 3.0e12f, 2); check(strcmp(b, "3.000e+12") == 0, std::string("fmt 3e12 -> ") + b);

    FlatObject o;
    check(parses("{\"a\":1,\"a\":2}", o) && o.get("a")->i == 2, "duplicate keys: last wins");
    check(parses(" {\"s\":\"x\\\"y\\u0041\"} ", o) && strcmp(o.get("s")->s, "x\"yA") == 0, "string escapes");
    check(parses("{\"n\":-0,\"f\":1.5e2,\"i\":2147483647,\"j\":2147483648}", o) && o.get("n")->type == V_INT &&
              o.get("f")->type == V_NUM && o.get("i")->type == V_INT && o.get("j")->type == V_NUM,
          "number types");
    check(!parses("{\"a\":{\"b\":1}}", o), "nested object rejected");
    check(!parses("{\"a\":[1]}", o), "array rejected");
    check(!parses("{\"a\":01}", o), "leading zero rejected");
    check(!parses("{\"a\":1}x", o), "trailing data rejected");
    check(!parses("{\"a\":1,}", o), "trailing comma rejected");
    check(!parses("{\"a\":\"0123456789abcdefX\"}", o), "overlong string rejected");
    check(!parses("{\"k0\":0,\"k1\":1,\"k2\":2,\"k3\":3,\"k4\":4,\"k5\":5,\"k6\":6,\"k7\":7,\"k8\":8,\"k9\":9,\"ka\":10}", o),
          "too many keys rejected");
    check(!parses("{\"a\":NaN}", o), "NaN rejected (flat JSON only)");

    char line[OUT_MAX];
    Writer w;
    w.begin(line, sizeof line); w.boolean("ok", true); w.integer("seq", 3); w.uinteger("t", 7);
    size_t n = w.finish();
    check(n > 0 && w.sorted && strcmp(line, "{\"ok\":true,\"seq\":3,\"t\":7,\"crc\":\"05\"}\n") == 0,
          std::string("writer output equals protocol.encode: ") + line);
    w.begin(line, sizeof line); w.integer("t", 1); w.integer("seq", 2); w.finish();
    check(!w.sorted, "writer flags unsorted keys");
    w.begin(line, 16); w.str("detail", "much too long for sixteen"); check(w.finish() == 0, "writer overflow returns 0");
}

// ------------------------------------------------------------------ script
static std::vector<std::string> split(const std::string& s, int max_parts) {
    std::vector<std::string> v;
    size_t i = 0;
    while (i <= s.size() && (int)v.size() < max_parts - 1) {
        size_t j = s.find(' ', i);
        if (j == std::string::npos) break;
        v.push_back(s.substr(i, j - i));
        i = j + 1;
    }
    v.push_back(s.substr(i));
    return v;
}

static int axis_of(const std::string& s) { return s == "st" ? 1 : 0; }

static void run_script(std::istream& in) {
    Rig rig;
    Config base;
    default_config(base);
    base.tt_release = 0;                            // the shared script checks TT holding; release is a bench option
    base.aug_timed = 0;                             // the shared script exercises the feedback mode; timed mode has fw-only checks
    Config cfg = base;
    double plant_rev_s = 1.2;
    rig.reset(true, 0, 0, cfg);
    std::string raw;
    int lineno = 0;
    while (std::getline(in, raw)) {
        lineno++;                                       // the script is written with bare '\n'; a '\r' is payload
        if (raw.empty() || raw[0] == '#') continue;
        if (raw.compare(0, 4, "sim ") == 0) continue;
        if (raw.compare(0, 3, "fw ") == 0) raw = raw.substr(3);
        std::ostringstream where;
        where << "line " << lineno << ": " << raw.substr(0, 90);
        std::vector<std::string> a = split(raw, 2);
        const std::string& op = a[0];
        std::string rest = a.size() > 1 ? a[1] : "";
        if (op == "reset") {
            bool known = rest.find("unknown") == std::string::npos;
            float tt = 0, st = 0;
            size_t p;
            if ((p = rest.find("tt=")) != std::string::npos) tt = (float)atof(rest.c_str() + p + 3);
            if ((p = rest.find("st=")) != std::string::npos) st = (float)atof(rest.c_str() + p + 3);
            rig.reset(known, tt, st, cfg);
            rig.plant.aug_rate = 360.0 / plant_rev_s;
        } else if (op == "cfg") {
            std::vector<std::string> kv = split(rest, 2);
            if (kv[0] == "plant_rev_s") { plant_rev_s = atof(kv[1].c_str()); rig.plant.aug_rate = 360.0 / plant_rev_s; }
            else check(set_field(cfg, kv[0], atof(kv[1].c_str())), where.str() + " (unknown config field)");
        } else if (op == "cfgclear") {
            cfg = base;
        } else if (op == "send") {
            rig.feed(rest);
        } else if (op == "long") {
            rig.feed(std::string((size_t)atoi(rest.c_str()), 'x'));
        } else if (op == "run") {
            rig.run((uint32_t)atoi(rest.c_str()));
        } else if (op == "estop") {
            rig.plant.estop = rest == "1";
        } else if (op == "jam") {
            rig.plant.jam = atoi(rest.c_str());
        } else if (op == "hx") {
            rig.plant.hx_on = rest == "1";
            if (rig.plant.hx_on) rig.plant.next_hx = rig.now + rig.plant.hx_period;
        } else if (op == "grams") {
            rig.plant.grams = atof(rest.c_str());
        } else if (op == "glitch") {                  // glitch MS OFFSET_DEG
            std::vector<std::string> v = split(rest, 2);
            rig.plant.glitch_until = rig.now + (uint32_t)atoi(v[0].c_str());
            rig.plant.glitch_deg = v.size() > 1 ? atof(v[1].c_str()) : 170.0;
        } else if (op == "mark") {
            rig.samples = 0;
            rig.progress.clear();
        } else if (op == "expect") {
            std::vector<std::string> v = split(rest, 2);
            std::string got = rig.kind(rig.first_reply(atoi(v[0].c_str())));
            check(got == v[1], where.str() + " -> got " + got);
        } else if (op == "expect_done") {
            std::vector<std::string> v = split(rest, 2);
            bool got = rig.has_done(atoi(v[0].c_str()));
            check(got == (v[1] == "1"), where.str() + (got ? " -> done seen" : " -> no done"));
        } else if (op == "expect_fault") {
            std::vector<std::string> v = split(rest, 2);
            bool got = false;
            for (size_t i = 0; i < rig.faults.size(); i++) got = got || rig.faults[i] == v[0];
            check(got == (v[1] == "1"), where.str() + (got ? " -> fault seen" : " -> no fault"));
        } else if (op == "expect_samples") {
            std::vector<std::string> v = split(rest, 2);
            std::ostringstream g;
            g << " -> " << rig.samples;
            check(rig.samples >= atoi(v[0].c_str()) && rig.samples <= atoi(v[1].c_str()), where.str() + g.str());
        } else if (op == "expect_progress") {
            std::vector<std::string> v = split(rest, 2);
            int got = rig.progress[atoi(v[0].c_str())];
            std::ostringstream g;
            g << " -> " << got;
            check(got >= atoi(v[1].c_str()), where.str() + g.str());
        } else if (op == "expect_num") {
            std::vector<std::string> v = split(rest, 4);
            const Tok* x = v.size() == 4 ? rig.last_value(atoi(v[0].c_str()), v[1].c_str()) : 0;
            bool ok = x && x->type == 'n' && x->num >= atof(v[2].c_str()) && x->num <= atof(v[3].c_str());
            std::ostringstream g;
            if (x) g << " -> " << x->num; else g << " -> missing";
            check(ok, where.str() + g.str());
        } else if (op == "expect_out") {
            std::vector<std::string> v = split(rest, 2);
            uint16_t us = v[0] == "aug" ? rig.core.aug_us() : (axis_of(v[0]) ? rig.core.st_us() : rig.core.tt_us());
            std::ostringstream g;
            g << " -> " << us << " us";
            check((us != 0) == (v[1] == "on"), where.str() + g.str());
        } else if (op == "expect_plant_deg") {        // the plant's real auger angle (net, signed)
            std::vector<std::string> v = split(rest, 2);
            std::ostringstream g;
            g << " -> " << rig.plant.aug_deg;
            check(rig.plant.aug_deg >= atof(v[0].c_str()) && rig.plant.aug_deg <= atof(v[1].c_str()), where.str() + g.str());
        } else if (op == "expect_known") {
            std::vector<std::string> v = split(rest, 2);
            check(rig.core.axis_known(axis_of(v[0])) == (v[1] == "1"), where.str());
        } else if (op == "expect_persist") {          // expect_persist tt|st KNOWN DEG
            std::vector<std::string> v = split(rest, 3);
            int ax = axis_of(v[0]);
            uint8_t k = ax ? rig.persisted.st_known : rig.persisted.tt_known;
            float d = ax ? rig.persisted.st_deg : rig.persisted.tt_deg;
            check(rig.persist_calls > 0 && k == atoi(v[1].c_str()) && fabs(d - atof(v[2].c_str())) < 0.01, where.str());
        } else if (op == "crc") {
            std::vector<std::string> v = split(rest, 2);
            std::string text = v.size() > 1 ? v[1] : "";
            unsigned want = (unsigned)strtoul(v[0].c_str(), 0, 16);
            check(crc8(text.data(), text.size()) == want, where.str());
        } else if (op == "v") {
            std::vector<std::string> v = split(rest, 3);
            rig.reset(true, 0, 0, cfg);
            rig.feed(v.size() > 2 ? v[2] : "");
            rig.run(200);
            std::string got = rig.kind(rig.first_reply(atoi(v[0].c_str())));
            check(got == v[1], where.str() + " -> got " + got);
        } else if (op == "echo") {
            printf("ECHO %s\n", rest.c_str());
        } else {
            check(false, where.str() + " (unknown script command)");
        }
    }
}

// ------------------------------------------------------------------ live mode (serial loopback over pipes)
#ifndef _WIN32
static uint32_t ms_since(const struct timeval& t0) {
    struct timeval t;
    gettimeofday(&t, 0);
    return (uint32_t)((t.tv_sec - t0.tv_sec) * 1000 + (t.tv_usec - t0.tv_usec) / 1000);
}

static void live_emit(void*, const char* line, size_t n) {
    fwrite(line, 1, n, stdout);
    fflush(stdout);
}

static int live(double grams) {
    Config cfg;
    default_config(cfg);
    cfg.tt_release = 0;
    cfg.aug_timed = 0;                              // the live plant simulates the feedback wire
    Plant plant;
    plant.grams = grams;
    plant.aug_rate = 360.0 / 1.2;
    Persist home;
    home.tt_deg = 0; home.st_deg = 0; home.tt_known = 1; home.st_known = 1;
    Core core;
    struct timeval t0;
    gettimeofday(&t0, 0);
    uint32_t last = 0;
    core.begin(cfg, 0, &home, live_emit, 0, 0);
    for (;;) {
        fd_set fds;
        FD_ZERO(&fds);
        FD_SET(0, &fds);
        struct timeval tv = {0, 500};
        if (select(1, &fds, 0, 0, &tv) > 0) {
            char buf[256];
            ssize_t n = read(0, buf, sizeof buf);
            if (n <= 0) return 0;                       // host closed the pipe
            uint32_t now = ms_since(t0);
            for (ssize_t i = 0; i < n; i++) core.feed(buf[i], now);
        }
        uint32_t now = ms_since(t0);
        while (last < now) {
            last++;
            plant.step(cfg, core.aug_us(), 1.0);
            if (last >= plant.next_hx) {
                plant.next_hx += plant.hx_period;
                core.hx_sample((int32_t)lround(plant.offset + (plant.grams + plant.noise_g * plant.gauss()) * plant.cpg), last);
            }
            core.tick(last, false, plant.adc(cfg, last));
        }
    }
}
#endif

int main(int argc, char** argv) {
    std::string script;
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "-v") g_verbose = true;
        else if (a == "--dump-config") {
            Config c;
            default_config(c);
            for (size_t k = 0; k < sizeof FIELDS / sizeof FIELDS[0]; k++) printf("CFG %s %.6f\n", FIELDS[k].name, get_field(c, FIELDS[k]));
            printf("CFG fw_id %s\n", WLB_FW_ID);
            return 0;
        } else if (a == "--live") {
#ifdef _WIN32
            fprintf(stderr, "--live needs POSIX select()\n");
            return 2;
#else
            double grams = i + 1 < argc ? atof(argv[i + 1]) : 0.0;
            return live(grams);
#endif
        } else script = a;
    }
    builtin_checks();
    if (!script.empty()) {
        if (script == "-") run_script(std::cin);
        else {
            std::ifstream f(script.c_str(), std::ios::binary);
            if (!f) { printf("FAIL cannot open %s\n", script.c_str()); g_fail++; }
            else run_script(f);
        }
    }
    printf("SUMMARY pass=%d fail=%d\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
