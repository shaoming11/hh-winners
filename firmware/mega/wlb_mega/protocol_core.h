// Wet Lab Bench Mega firmware: protocol, validation and motion/state logic.
//
// Pure C++11 with no Arduino headers, so the same file is compiled into the sketch (avr-gcc) and into the
// host test (firmware/mega/host_test/test_protocol_core.cpp). The sketch (wlb_mega.ino) owns the pins,
// Timer4, the HX711 bit-bang, the A2 ADC read and EEPROM; this core only sees numbers:
//
//     feed(char)                bytes from the host serial port
//     hx_sample(raw)            one HX711 conversion (24-bit signed counts)
//     tick(now, estop, adc)     every loop pass: e-stop input (true = D2 HIGH = open), auger feedback ADC
//     tt_us() st_us() aug_us()  pulse widths to load into OCR4A/B/C; 0 = output off (pin LOW, no pulses)
//
// The wire protocol is software/benchsim/benchsim/protocol.py (one JSON object per line, sorted keys, a
// trailing ,"crc":"xx"} CRC-8/ATM over the body text). The behaviour follows the simulated Mega in
// software/benchsim/benchsim/backends/sim.py; firmware-only differences are listed in firmware/mega/README.md.
//
// Floats are 32-bit here (avr double is float); all arithmetic uses float so the host test sees the same
// rounding as the board.
#ifndef WLB_PROTOCOL_CORE_H
#define WLB_PROTOCOL_CORE_H

#include <stddef.h>
#include <stdint.h>

#define WLB_FW_ID "wlb-mega 0.1"

namespace wlb {

enum {
    IN_MAX = 160,       // longest accepted input line (protocol lines are < 80 characters)
    OUT_MAX = 200,        // longest output line
    MAX_KEYS = 10,        // flat object: at most this many keys
    KEY_MAX = 15,         // longest key
    STR_MAX = 15,         // longest string value
    DETAIL_MAX = 72,      // error detail text
};

// ------------------------------------------------------------------ CRC and codes
uint8_t crc8(const char* data, size_t n);              // CRC-8/ATM: poly 0x07, init 0, no reflection

enum Err { E_NONE = 0, E_BADCMD, E_RANGE, E_BUSY, E_STATE, E_ESTOP, E_CRC };
const char* err_name(int e);

enum Fault {                                           // bit flags, protocol.FAULTS order
    F_ESTOP = 1 << 0, F_AUGER_JAM = 1 << 1, F_HOPPER_EMPTY = 1 << 2, F_HX_TIMEOUT = 1 << 3,
    F_WDT = 1 << 4, F_TT_TIMEOUT = 1 << 5, F_ST_TIMEOUT = 1 << 6, F_AUG_TIMEOUT = 1 << 7,
};
const char* fault_name(uint16_t f);                    // single flag -> name

enum Cmd { C_UNKNOWN = 0, C_PING, C_TT, C_ST, C_AUG, C_TARE, C_CAL, C_STREAM, C_STOP, C_CLR, C_HB };

// ------------------------------------------------------------------ flat JSON
enum ValType { V_NULL = 0, V_BOOL, V_INT, V_NUM, V_STR };

struct Value {
    uint8_t type;
    bool b;
    int32_t i;                 // V_INT (and V_BOOL as 0/1)
    float f;                   // V_INT and V_NUM
    char s[STR_MAX + 1];       // V_STR
};

struct FlatObject {
    uint8_t n;
    char keys[MAX_KEYS][KEY_MAX + 1];
    Value vals[MAX_KEYS];
    const Value* get(const char* key) const;
};

// Parse one flat JSON object (string/number/true/false/null values only). Returns false and points err at
// a short reason on malformed input, nesting, overlong keys/strings or too many keys. Duplicate keys keep
// the last value, as Python's json does.
bool parse_flat_json(const char* s, size_t n, FlatObject& out, const char** err);

// protocol.decode: strip, check the trailing CRC field if present, parse. Returns E_NONE, E_CRC or E_BADCMD.
int decode_line(const char* line, size_t n, FlatObject& out, char* detail, size_t detail_n);

// ------------------------------------------------------------------ output lines
// Builds {"k":v,...,"crc":"xx"}\n. Keys must be added in sorted order (protocol.encode sorts them); an
// out-of-order key clears `sorted` so the host test can catch it.
class Writer {
public:
    void begin(char* buf, size_t cap);
    void str(const char* k, const char* v);
    void boolean(const char* k, bool v);
    void integer(const char* k, int32_t v);
    void uinteger(const char* k, uint32_t v);
    void num(const char* k, float v, uint8_t decimals);   // NaN/inf -> null
    void null(const char* k);
    size_t finish();                                       // length including '\n', 0 on overflow
    bool sorted;
private:
    void key(const char* k);
    void put(const char* s);
    void putc_(char c);
    char* buf_;
    size_t cap_, n_;
    bool ok_;
    char last_[KEY_MAX + 1];
};

size_t fmt_num(char* out, size_t cap, float v, uint8_t decimals);   // fixed point, trailing zeros trimmed

// ------------------------------------------------------------------ configuration
// Every value mirrors software/benchsim/benchsim/config/bench_params.toml ([carousel] [stage] [auger] [scale]
// [mega]) or a constant of protocol.validate; tests/test_firmware_core.py fails if they disagree.
struct ServoCal {
    float us_at_zero;          // pulse at 0 deg
    float us_per_deg;          // may be negative (servo mounted reversed)
};

struct Config {
    // protocol.Limits / protocol.validate
    float tt_lo_deg, tt_hi_deg, tt_ms_per_45, tt_slack_ms;
    float st_lo_deg, st_hi_deg, st_ms_min;
    float aug_rev_max;
    float cpg_lo, cpg_hi;
    // timing
    uint32_t wdt_ms, tt_extra_ms, st_extra_ms, settle_ms, aug_timeout_ms, progress_ms, estop_release_ms;
    uint32_t hx_timeout_min_ms;
    uint8_t hx_timeout_intervals, tare_samples;
    float hx_nominal_ms;
    float counts_per_g;
    // servos (M45CHW): pulse = us_at_zero + us_per_deg * deg
    ServoCal tt, st;
    uint16_t us_min, us_max;
    float home_tt_deg, home_st_deg;
    // auger (FB5311M-360)
    uint16_t aug_us_stop, aug_us_offset;
    int8_t aug_dir_sign;       // pulse offset sign for dir = +1
    int8_t aug_fb_sign;        // feedback angle change sign when the pulse is above the stop centre
    uint8_t aug_timed;         // 1 = no feedback wire: progress from time at aug_rev_per_s, no stall rule
    float aug_rev_per_s;       // measured auger speed at aug_us_offset (timed mode)
    uint32_t aug_start_ms;     // timed mode: spin-up time not counted as progress at the start of each dose
    float aug_coast_rev;       // timed mode: turns the screw coasts after the stop pulse; credited at the start of a dose
    uint8_t tt_release;        // 1 = stop the TT pulses once a move is done (heavy deck: the servo's own loop hunts while holding)
    // closed-loop carousel (tt_closed = 1): continuous servo on D6 + its analog position feedback on A3.
    // deck angle = tt_fb_sign * feedback angle - tt_fb_zero_deg (wrapped into the deck range); the target follows the
    // same smooth profile as the open-loop move; pulse = tt_us_stop + tt_dir_sign * clamp(kp*err - kd*vel, +-tt_max_off)
    uint8_t tt_closed;
    uint16_t tt_adc_min, tt_adc_max; // feedback ADC over one turn
    int8_t tt_fb_sign;         // +1: feedback angle grows with the deck angle
    int8_t tt_dir_sign;        // +1: a pulse above tt_us_stop turns the deck toward + deg
    float tt_fb_zero_deg;      // feedback angle (after tt_fb_sign) at deck 0
    uint16_t tt_us_stop;       // continuous servo stop centre
    float tt_kp;               // us per deg of error
    float tt_kd;               // us per deg/s of measured speed
    uint16_t tt_max_off;       // largest pulse offset from the stop centre
    float tt_tol_deg;          // done when within this for settle_ms after the profile
    float tt_db_deg;           // after the profile, no drive inside this error (stops the hunting)
    uint16_t aug_adc_min, aug_adc_max;
    uint32_t stall_window_ms;
    float stall_min_deg;
    uint8_t max_stalls;
    float reverse_deg;
    float fb_max_step_deg;     // larger jumps between two loop passes are feedback glitches
    uint8_t fb_glitch_resync;  // after this many glitches in a row, resynchronise without counting
};

void default_config(Config& c);
bool config_covers_limits(const Config& c);            // every protocol degree maps into [us_min, us_max]

// Rest positions the sketch keeps in EEPROM. known = 0 while a move runs, so a reset mid-move boots unknown.
struct Persist {
    float tt_deg, st_deg;
    uint8_t tt_known, st_known;
};

// ------------------------------------------------------------------ the core
class Core {
public:
    typedef void (*EmitFn)(void* ctx, const char* line, size_t n);
    typedef void (*PersistFn)(void* ctx, const Persist& p);

    enum Motion { M_NONE = 0, M_TT, M_ST, M_AUG };
    enum AugPhase { A_DOSE = 0, A_REVERSE, A_FINISH };

    void begin(const Config& cfg, uint32_t now, const Persist* restored, EmitFn emit, PersistFn persist, void* ctx);
    void feed(char c, uint32_t now);
    void handle_line(const char* line, size_t n, uint32_t now);
    void hx_sample(int32_t raw, uint32_t now);
    void tick(uint32_t now, bool estop_open, uint16_t aug_adc);
    void set_tt_adc(uint16_t adc) { tt_adc_ = adc; }   // closed-loop carousel feedback (A3); call before tick()
    float tt_measured() const;                          // deck angle from the A3 feedback

    uint16_t tt_us() const { return ax_[0].driven ? (uint16_t)(ax_[0].us + 0.5f) : 0; }
    uint16_t st_us() const { return ax_[1].driven ? (uint16_t)(ax_[1].us + 0.5f) : 0; }
    uint16_t aug_us() const { return aug_out_; }

    // state, for the host test and the sketch
    uint16_t faults() const { return faults_; }
    uint8_t motion() const { return motion_; }
    bool streaming() const { return streaming_; }
    bool axis_known(int i) const { return ax_[i].known; }
    float axis_deg(int i) const { return ax_[i].rest_deg; }
    float hx_interval_ms() const { return hx_interval_; }
    uint8_t aug_stalls() const { return aug_.stalls; }
    float aug_rev() const { return aug_.hw / 360.0f; }
    uint32_t unsorted_lines() const { return unsorted_; }
    const Config& config() const { return cfg_; }

private:
    struct Axis {
        float rest_deg, cur_deg, us;
        bool known, driven;
    };
    struct AxisMove {
        int32_t seq;
        uint32_t t0;
        float dur_ms, timeout_ms, deg0, deg1, us0, us1;
    };
    struct Auger {
        int32_t seq;
        uint32_t t0, win_t0, next_prog, last_t;
        float target, net, hw, win_net, rev_until, last_fb;
        int8_t dir;
        uint8_t phase, after, stalls, glitches;
        bool fb_init;
    };

    int validate(const FlatObject& o, uint8_t& cmd, char* detail);
    bool current_deg(int axis, float& deg) const;
    float deg_to_us(int axis, float deg) const;
    void start_axis(int axis, int32_t seq, float deg, float ms, uint32_t now);
    void start_auger(int32_t seq, float rev, int8_t dir, uint32_t now);
    void axis_tick(uint32_t now);
    void tt_closed_tick(uint32_t now, float el, float s);
    void auger_tick(uint32_t now, uint16_t adc);
    void begin_reverse(uint32_t now, uint8_t after);
    float fb_angle(uint16_t adc) const;
    void fault(uint16_t f, uint32_t now);
    void all_off();
    void save();
    uint32_t hx_timeout_ms() const;
    bool estop_released(uint32_t now) const;

    void reply_err(int32_t seq, int code, const char* detail, uint32_t now);
    void reply_simple(int32_t seq, const char* key, uint32_t now);
    void reply_ping(int32_t seq, uint32_t now);
    void emit_boot(uint32_t now);
    void send(Writer& w);

    Config cfg_;
    EmitFn emit_;
    PersistFn persist_;
    void* ctx_;
    char line_[IN_MAX + 1];
    size_t line_n_;
    bool overflow_;
    FlatObject obj_;             // the command being handled (static, not on the AVR stack)
    char out_[OUT_MAX];
    uint32_t unsorted_;

    uint16_t faults_;
    uint8_t motion_;
    bool armed_;
    uint32_t last_rx_, now_;
    bool estop_low_valid_;
    uint32_t estop_low_since_;
    bool estop_in_;
    uint16_t adc_;
    uint16_t tt_adc_;
    float tt_prev_meas_, tt_vel_;
    uint32_t tt_prev_t_, tt_tol_since_;
    bool tt_tol_on_;

    Axis ax_[2];
    AxisMove mv_;
    Auger aug_;
    uint16_t aug_out_;

    bool streaming_;
    float counts_per_g_;
    bool tared_;
    int32_t tare_counts_;
    bool tare_pending_;
    int32_t tare_seq_;
    uint8_t tare_n_;
    int64_t tare_sum_;           // 64-bit: up to 255 samples of 24-bit counts
    bool hx_seen_;
    uint32_t hx_last_, hx_ref_;
    float hx_interval_;
};

}  // namespace wlb

#endif
