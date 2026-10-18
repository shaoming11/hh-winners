// Wet Lab Bench: Arduino Mega 2560 (Pro) firmware.
//
// Pins and timers: docs/electrical.md 4. Wire protocol: software/benchsim/benchsim/protocol.py (JSON lines,
// 250000 baud). All parsing, validation, faults and motion logic live in protocol_core.cpp, which is compiled
// and tested on the host (firmware/mega/host_test). This file only moves numbers between the core and the pins.
// No external libraries: EEPROM is part of the Arduino AVR core.
//
// Power-up safety (electrical.md 2): D6/D7/D8 are driven LOW from .init3, before the C runtime and setup(), and
// Timer4 runs with its compare outputs disconnected, so no servo sees a pulse until the host sends TT/ST/AUG.
// Press the e-stop before plugging in the pack and before flashing or resetting the board.
#include <Arduino.h>
#include <EEPROM.h>
#include <avr/interrupt.h>
#include <avr/io.h>

#include "protocol_core.h"

// ------------------------------------------------------------------ pins (electrical.md 4)
#define ESTOP_PIN 2                 // D2 = PE4 / INT4: NC contact to GND, INPUT_PULLUP; HIGH = pressed or wire broken
#define ESTOP_BIT _BV(PE4)
// No e-stop on this bench (decided 2026-10-17: water dry runs, unplugging the pack is the stop). D2 is ignored by
// default; build with -DWLB_USE_ESTOP to wire one back in (NC contact D2 -> GND, latches like before).
#ifndef WLB_USE_ESTOP
#define WLB_NO_ESTOP
#endif
#ifdef WLB_NO_ESTOP
#define ESTOP_OPEN() false
#else
#define ESTOP_OPEN() ((PINE & ESTOP_BIT) != 0)
#endif
#define HX_DT_BIT _BV(PC6)          // D31 = PC6: HX711 DOUT (D3 -> D11 -> D31 to fit the bench wiring)
#define HX_DT_PIN PINC
#define HX_DT_DDR DDRC
#define HX_DT_PORT PORTC
#define HX_SCK_BIT _BV(PG5)         // D4 = PG5: HX711 SCK, written on PORTG
#define TT_BIT _BV(PH3)             // D6 = PH3 / OC4A: carousel M45CHW
#define ST_BIT _BV(PH4)             // D7 = PH4 / OC4B: stage M45CHW
#define AUG_BIT _BV(PH5)            // D8 = PH5 / OC4C: auger FB5311M-360
#define SERVO_BITS (TT_BIT | ST_BIT | AUG_BIT)
#define AUG_FB_PIN A2               // A2 = PF2 / ADC2: auger position feedback (AVcc reference)
#define TT_FB_PIN A3                // A3 = PF3 / ADC3: carousel continuous-servo position feedback (tt_closed)

#define COM_TT _BV(COM4A1)
#define COM_ST _BV(COM4B1)
#define COM_AUG _BV(COM4C1)
#define COM_ALL (_BV(COM4A1) | _BV(COM4A0) | _BV(COM4B1) | _BV(COM4B0) | _BV(COM4C1) | _BV(COM4C0))

static const uint16_t FRAME_TOP = 39999;        // Timer4 mode 14, prescaler 8: 16 MHz / 8 / 40000 = 50 Hz
static const uint8_t EE_MAGIC = 0xB5, EE_VERSION = 1;
static const int EE_ADDR = 0;

static wlb::Core core;
static volatile bool estop_isr = false;         // set by the D2 interrupt, read and cleared in loop()
static volatile uint8_t com_pending = 0;        // compare outputs to connect at the next frame start

// ------------------------------------------------------------------ earliest boot: servo signals LOW
#ifdef __AVR__
void wlb_servo_pins_low(void) __attribute__((naked, used, section(".init3")));
void wlb_servo_pins_low(void) {
    PORTH &= ~SERVO_BITS;
    DDRH |= SERVO_BITS;
}
#endif

// ------------------------------------------------------------------ Timer4 servo PWM, no Servo library
static void pwm_init() {
    uint8_t s = SREG;
    cli();
    TIMSK4 = 0;
    TCCR4A = 0;                                 // COM4x = 0: pins are plain outputs, held LOW
    TCCR4B = 0;
    TCCR4C = 0;
    TCNT4 = 0;
    ICR4 = FRAME_TOP;
    OCR4A = OCR4B = OCR4C = 3000;               // placeholders while disconnected
    TCCR4A = _BV(WGM41);                        // mode 14: fast PWM, TOP = ICR4
    TCCR4B = _BV(WGM43) | _BV(WGM42) | _BV(CS41);
    TIFR4 = _BV(TOV4);
    TIMSK4 = _BV(TOIE4);
    SREG = s;
}

// Connecting a compare output mid-frame could emit one truncated pulse; outputs are connected here, at the
// frame start, so the first pulse is always whole. OCR4x is double-buffered and also loads at BOTTOM.
ISR(TIMER4_OVF_vect) {
    if (com_pending && !ESTOP_OPEN()) TCCR4A |= com_pending;
    com_pending = 0;
}

static void cut_all_pwm() {                     // call with interrupts off or from an ISR
    TCCR4A &= ~COM_ALL;
    PORTH &= ~SERVO_BITS;
    com_pending = 0;
}

static void on_estop() {                        // D2 rising: e-stop pressed or wire broken
    cut_all_pwm();
    estop_isr = true;
}

static void apply_channel(uint16_t us, volatile uint16_t* ocr, uint8_t com, uint8_t bit) {
    uint8_t s = SREG;
    cli();
    if (us == 0) {                              // output off: disconnect, pin LOW, no pulses
        TCCR4A &= ~com;
        PORTH &= ~bit;
        com_pending &= ~com;
    } else {
        *ocr = (uint16_t)(2 * us);              // OCR4x = 2 x us (0.5 us per timer tick)
        if (!(TCCR4A & com)) com_pending |= com;
    }
    SREG = s;
}

static void apply_outputs(bool estop_open) {
    if (estop_open) {
        uint8_t s = SREG;
        cli();
        cut_all_pwm();
        SREG = s;
        return;
    }
    apply_channel(core.tt_us(), &OCR4A, COM_TT, TT_BIT);
    apply_channel(core.st_us(), &OCR4B, COM_ST, ST_BIT);
    apply_channel(core.aug_us(), &OCR4C, COM_AUG, AUG_BIT);
}

// ------------------------------------------------------------------ HX711, bit-banged (gain 128, channel A)
static void hx_init() {
    HX_DT_DDR &= ~HX_DT_BIT;
    HX_DT_PORT &= ~HX_DT_BIT;
    PORTG &= ~HX_SCK_BIT;                       // SCK LOW: SCK held HIGH > 60 us powers the HX711 down
    DDRG |= HX_SCK_BIT;
}

static bool hx_ready() { return !(HX_DT_PIN & HX_DT_BIT); }

static int32_t hx_read() {
    uint32_t v = 0;
    uint8_t s = SREG;
    cli();                                      // interrupts off only for the 25 clocks, about 25 us
    for (uint8_t i = 0; i < 24; i++) {
        PORTG |= HX_SCK_BIT;
        __builtin_avr_delay_cycles(4);          // SCK high >= 0.2 us, data valid 0.1 us after the edge
        v = (v << 1) | ((HX_DT_PIN & HX_DT_BIT) ? 1u : 0u);
        PORTG &= ~HX_SCK_BIT;
        __builtin_avr_delay_cycles(4);
    }
    PORTG |= HX_SCK_BIT;                        // 25th pulse: next conversion on channel A, gain 128
    __builtin_avr_delay_cycles(4);
    PORTG &= ~HX_SCK_BIT;
    SREG = s;
    if (v & 0x800000UL) v |= 0xFF000000UL;      // 24-bit two's complement
    return (int32_t)v;
}

// ------------------------------------------------------------------ EEPROM rest positions
struct Record {
    uint8_t magic, version;
    wlb::Persist p;
    uint8_t crc;
};

static void persist(void*, const wlb::Persist& p) {
    Record r;
    r.magic = EE_MAGIC;
    r.version = EE_VERSION;
    r.p = p;
    r.crc = wlb::crc8((const char*)&r.p, sizeof r.p);
    EEPROM.put(EE_ADDR, r);                     // update(): only changed bytes are written (about 3.4 ms each)
}

static bool restore(wlb::Persist& p) {
    Record r;
    EEPROM.get(EE_ADDR, r);
    if (r.magic != EE_MAGIC || r.version != EE_VERSION || r.crc != wlb::crc8((const char*)&r.p, sizeof r.p)) return false;
    p = r.p;
    return true;
}

static void emit(void*, const char* line, size_t n) { Serial.write((const uint8_t*)line, n); }

// ------------------------------------------------------------------ Arduino entry points
void setup() {
    PORTH &= ~SERVO_BITS;                       // again, in case .init3 was not linked
    DDRH |= SERVO_BITS;
    pwm_init();
    hx_init();
    pinMode(ESTOP_PIN, INPUT_PULLUP);
#ifndef WLB_NO_ESTOP
    attachInterrupt(digitalPinToInterrupt(ESTOP_PIN), on_estop, RISING);
#endif
    analogReference(DEFAULT);                   // AVcc
    Serial.begin(250000);
    wlb::Config cfg;
    wlb::default_config(cfg);
    wlb::Persist p;
    bool ok = restore(p);
    core.begin(cfg, millis(), ok ? &p : 0, emit, persist, 0);   // prints the boot line
}

void loop() {
    while (Serial.available() > 0) core.feed((char)Serial.read(), millis());
    if (hx_ready()) core.hx_sample(hx_read(), millis());
    bool estop = ESTOP_OPEN();
    if (estop_isr) {
        estop_isr = false;
        estop = true;
    }
    core.set_tt_adc((uint16_t)analogRead(TT_FB_PIN));
    core.tick(millis(), estop, (uint16_t)analogRead(AUG_FB_PIN));
    apply_outputs(estop);
}
