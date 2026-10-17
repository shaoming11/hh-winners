"""Mega firmware core on the host (firmware/mega): compiled with the system C++ compiler and fed lines from
benchsim.protocol.encode. The same scenario script also runs against the simulated Mega, so firmware and
simulator are held to one set of expectations. Skips (with the reason) when no compiler is installed."""
import os
import subprocess
import threading
import time

import pytest

from benchsim import protocol
from benchsim.backends import real, sim
from benchsim.interfaces import MegaClient, MegaError
from benchsim.layout import load_params

CXX = real.find_cxx()
needs_cxx = pytest.mark.skipif(CXX is None, reason='no C++ compiler (c++, clang++ or g++) on PATH: firmware host test not run')


@pytest.fixture(scope='module')
def fw_build(tmp_path_factory):
    if CXX is None: pytest.skip('no C++ compiler (c++, clang++ or g++) on PATH: firmware host test not run')
    return real.build_firmware_host_test(tmp_path_factory.mktemp('fw'))


@pytest.fixture(scope='module')
def script():
    return real.firmware_test_script()


@pytest.fixture(scope='module')
def fw_run(fw_build, script):
    return real.run_firmware_host_test(fw_build['exe'], script)


# ------------------------------------------------------------------ the C++ host test
@needs_cxx
def test_firmware_core_compiles_without_warnings(fw_build):
    fw = [l for l in fw_build['warnings'].splitlines() if 'wlb_mega/' in l]       # the harness may warn on other compilers
    assert fw == [], fw_build['warnings']


@needs_cxx
def test_firmware_host_test_passes(fw_run, script):
    assert fw_run['ok'], fw_run['failures'][:20]
    n_v = sum(l.startswith(('v ', 'fw v ')) for l in script.splitlines())
    n_crc = sum(l.startswith('crc ') for l in script.splitlines())
    assert n_v >= 180 and n_crc == 40 and fw_run['passed'] > n_v + n_crc + 50


@needs_cxx
def test_every_firmware_line_decodes_in_python(fw_run):
    """CRC agreement in the other direction: protocol.decode checks the CRC of every line the firmware wrote"""
    assert len(fw_run['out_lines']) > 500
    assert real.check_output_lines(fw_run['out_lines']) == []
    kinds = {k for l in fw_run['out_lines'] for k in ('ack', 'ok', 'done', 'err', 'w', 'aug', 'fault', 'boot') if k in protocol.decode(l)}
    assert kinds == {'ack', 'ok', 'done', 'err', 'w', 'aug', 'fault', 'boot'}


@needs_cxx
def test_firmware_constants_match_bench_params(fw_build):
    assert real.firmware_config_parity(real.dump_firmware_config(fw_build['exe'])) == []


def test_firmware_timing_constants_match_simmega():
    P = load_params()
    assert sim.SimMega.WDT_S * 1000 == P['mega']['wdt_ms'] and sim.SimMega.PROGRESS_S * 1000 == P['mega']['progress_ms']


def test_validation_vectors_reach_every_outcome():
    lim = protocol.Limits(load_params()); cur = dict(tt_deg=0.0, st_deg=0.0)
    kinds = {real.expected_reply(line, lim, cur)[1] for line, _ in real.validation_vectors(lim)}
    assert kinds == {'ack', 'ok', 'none', 'err:BADCMD', 'err:RANGE', 'err:CRC'}


# ------------------------------------------------------------------ the same script against the simulated Mega
class SimScript:
    """runs the firmware test script against benchsim.backends.sim.SimMega; 'fw ' lines are skipped"""

    def __init__(self, built):
        self.model, self.b = built; self.failures = []; self.checks = 0; self.reset()

    def reset(self):
        self.w = sim.SimWorld(model=self.model, builder=self.b); self.mega = sim.SimMega(self.w)
        self.by_seq = {}; self.first = None; self.faults = []; self.samples = 0; self.progress = {}

    def pump(self):
        for line in self.mega.drain():
            msg = protocol.decode(line)
            if 'w' in msg: self.samples += 1
            elif 'fault' in msg: self.faults.append(msg['fault'])
            elif 'aug' in msg: self.progress[msg['seq']] = self.progress.get(msg['seq'], 0) + 1
            elif 'seq' in msg:
                self.by_seq.setdefault(msg['seq'], []).append(msg); self.first = self.first or msg

    @staticmethod
    def kind(m):
        if m is None: return 'none'
        for k in ('ack', 'ok', 'done'):
            if m.get(k): return k
        return 'err:' + m['err'] if 'err' in m else '?'

    def check(self, ok, what):
        self.checks += 1
        if not ok: self.failures.append(what)

    def execute(self, text):
        for no, raw in enumerate(text.split('\n'), 1):
            if not raw or raw.startswith(('#', 'fw ')): continue
            if raw.startswith('sim '): raw = raw[4:]
            op, _, rest = raw.partition(' '); a = rest.split(' '); where = 'line %d: %s' % (no, raw[:90])
            if op == 'reset': self.reset()
            elif op in ('cfg', 'cfgclear', 'crc', 'echo'): pass
            elif op == 'send': self.mega.receive(rest + '\n')
            elif op == 'run': self.w.advance(int(rest) / 1000.0); self.pump()
            elif op == 'estop': self.w.estop = rest == '1'
            elif op == 'jam': self.w.auger_jam = rest != '0'
            elif op == 'hx': self.w.hx_fail = rest == '0'
            elif op == 'mark': self.samples = 0; self.progress = {}
            elif op == 'expect':
                got = self.kind((self.by_seq.get(int(a[0])) or [None])[0]); self.check(got == a[1], '%s -> got %s' % (where, got))
            elif op == 'expect_done':
                got = any(m.get('done') for m in self.by_seq.get(int(a[0]), [])); self.check(got == (a[1] == '1'), '%s -> %s' % (where, got))
            elif op == 'expect_fault':
                got = a[0] in self.faults; self.check(got == (a[1] == '1'), '%s -> %s' % (where, self.faults))
            elif op == 'expect_samples':
                self.check(int(a[0]) <= self.samples <= int(a[1]), '%s -> %d' % (where, self.samples))
            elif op == 'expect_progress':
                got = self.progress.get(int(a[0]), 0); self.check(got >= int(a[1]), '%s -> %d' % (where, got))
            elif op == 'expect_num':
                vals = [m[a[1]] for m in self.by_seq.get(int(a[0]), []) if a[1] in m]
                self.check(bool(vals) and float(a[2]) <= vals[-1] <= float(a[3]), '%s -> %s' % (where, vals))
            elif op == 'v':
                _, kind, line = rest.split(' ', 2)
                self.reset(); self.mega.receive(line + '\n'); self.w.advance(0.2); self.pump()
                got = self.kind(self.first); self.check(got == kind, '%s -> got %s' % (where, got))
            else: self.check(False, where + ' (unknown op for the simulator)')


def test_simulated_mega_meets_the_same_script(built, script):
    s = SimScript(built); s.execute(script)
    assert s.checks >= 250 and s.failures == [], s.failures[:20]


# ------------------------------------------------------------------ the sketch against stub AVR registers
STUB_ARDUINO = r'''
#pragma once
#include <stdint.h>
#include <stddef.h>
#include <deque>
#include <string>
#define _BV(b) (1 << (b))
extern volatile uint8_t PORTE, DDRE, PINE, PORTG, DDRG, PORTH, DDRH, TCCR4A, TCCR4B, TCCR4C, TIMSK4, TIFR4, SREG;
extern volatile uint16_t TCNT4, ICR4, OCR4A, OCR4B, OCR4C;
enum { PE3 = 3, PE4 = 4, PE5 = 5, PG5 = 5, PH3 = 3, PH4 = 4, PH5 = 5, COM4A1 = 7, COM4A0 = 6, COM4B1 = 5, COM4B0 = 4, COM4C1 = 3,
       COM4C0 = 2, WGM41 = 1, WGM43 = 4, WGM42 = 3, CS41 = 1, TOV4 = 0, TOIE4 = 0 };
#define A2 56
#define INPUT_PULLUP 2
#define RISING 3
#define DEFAULT 1
#define ISR(v) extern "C" void v(void)
#define __builtin_avr_delay_cycles(n) ((void)0)
inline void cli() {}
inline void sei() {}
uint32_t millis();
int analogRead(uint8_t);
void analogReference(uint8_t);
void pinMode(uint8_t, uint8_t);
inline int digitalPinToInterrupt(uint8_t p) { return p == 2 ? 4 : -1; }
void attachInterrupt(int, void (*)(void), int);
struct StubSerial {
    std::deque<char> rx; std::string tx;
    void begin(long) {}
    int available() { return (int)rx.size(); }
    int read() { char c = rx.front(); rx.pop_front(); return (unsigned char)c; }
    size_t write(const uint8_t* b, size_t n) { tx.append((const char*)b, n); return n; }
};
extern StubSerial Serial;
'''

STUB_EEPROM = r'''
#pragma once
#include <string.h>
struct StubEEPROM {
    uint8_t mem[4096];
    StubEEPROM() { memset(mem, 0xFF, sizeof mem); }
    template <class T> T& get(int a, T& t) { memcpy(&t, mem + a, sizeof t); return t; }
    template <class T> const T& put(int a, const T& t) { memcpy(mem + a, &t, sizeof t); return t; }
};
extern StubEEPROM EEPROM;
'''

SMOKE = r'''
#include <stdio.h>
#include "Arduino.h"
#include "EEPROM.h"
volatile uint8_t PORTE, DDRE, PINE, PORTG, DDRG, PORTH, DDRH, TCCR4A, TCCR4B, TCCR4C, TIMSK4, TIFR4, SREG;
volatile uint16_t TCNT4, ICR4, OCR4A, OCR4B, OCR4C;
StubSerial Serial;
StubEEPROM EEPROM;
static uint32_t g_ms = 0;
static void (*g_isr)(void) = 0;
uint32_t millis() { return g_ms; }
int analogRead(uint8_t) { return 0; }
void analogReference(uint8_t) {}
void pinMode(uint8_t, uint8_t) {}
void attachInterrupt(int n, void (*f)(void), int) { if (n == 4) g_isr = f; }
#include "SKETCH"
static int fails = 0;
#define CHECK(c, m) do { if (c) printf("PASS %s\n", m); else { printf("FAIL %s\n", m); fails++; } } while (0)
static void feed(const char* l) { while (*l) Serial.rx.push_back(*l++); Serial.rx.push_back('\n'); }
static void step(int ms) { for (int i = 0; i < ms; i++) { g_ms++; loop(); if (g_ms % 20 == 0) TIMER4_OVF_vect(); } }
static bool sent(const char* s) { return Serial.tx.find(s) != std::string::npos; }
int main(int argc, char** argv) {
    if (argc < 4) return 2;
    PORTH = 0xFF; DDRH = 0; TCCR4A = 0xFF; PINE = HX_DT_BIT;          /* pins high before boot; HX711 not ready */
    setup();
    CHECK((PORTH & SERVO_BITS) == 0 && (DDRH & SERVO_BITS) == SERVO_BITS, "D6/D7/D8 are LOW outputs after setup");
    CHECK(TCCR4A == _BV(WGM41) && TCCR4B == (_BV(WGM43) | _BV(WGM42) | _BV(CS41)) && ICR4 == 39999, "Timer4 mode 14, prescaler 8, 20 ms frame");
    CHECK((TCCR4A & COM_ALL) == 0 && TIMSK4 == _BV(TOIE4), "compare outputs disconnected at boot");
    CHECK(sent("\"boot\":true") && sent("\"pos\":\"unknown\""), "boot line; blank EEPROM boots with position unknown");
    step(400);
    CHECK((TCCR4A & COM_ALL) == 0 && (PORTH & SERVO_BITS) == 0, "no pulses without a command");
    feed(argv[1]); step(5);
    CHECK((TCCR4A & COM_ALL) == 0, "CLR home does not start pulses");
    feed(argv[2]); g_ms++; loop();
    CHECK((TCCR4A & COM_TT) == 0 && (com_pending & COM_TT), "TT output waits for the frame start");
    TIMER4_OVF_vect();
    CHECK((TCCR4A & COM_TT) && !(TCCR4A & (COM_ST | COM_AUG)), "only the carousel output is connected");
    CHECK(OCR4A == 2 * 569, "first pulse = rest position (569 us at 0 deg), OCR4A = 2 x us");
    for (int i = 0; i < 10; i++) { feed(argv[3]); step(100); }
    CHECK(OCR4A > 2 * 580 && OCR4A < 2 * 638, "pulse ramps toward 10 deg (638 us); about 603 us halfway");
    PINE |= ESTOP_BIT; g_isr();
    CHECK((TCCR4A & COM_ALL) == 0 && (PORTH & SERVO_BITS) == 0, "D2 interrupt cuts all PWM at once");
    TIMER4_OVF_vect(); step(5);
    CHECK((TCCR4A & COM_ALL) == 0 && sent("\"fault\":\"ESTOP\""), "outputs stay off; ESTOP fault sent");
    CHECK(EEPROM.mem[0] == EE_MAGIC, "rest positions persisted to EEPROM");
    Serial.tx.clear(); PINE &= ~ESTOP_BIT; setup();
    CHECK(sent("\"pos\":\"unknown\"") && sent("\"tt\":null") && sent("\"st\":0.0"), "after a reset mid-move the carousel boots unknown, the stage known");
    printf("SUMMARY fails=%d\n", fails);
    return fails ? 1 : 0;
}
'''


@needs_cxx
def test_sketch_register_logic_against_stub_avr_registers(tmp_path):
    """host smoke test of wlb_mega.ino with stub AVR registers (checks the register logic, not avr-gcc output or
    real timing; a logic analyser capture at bring-up is still needed)"""
    (tmp_path / 'avr').mkdir()
    (tmp_path / 'Arduino.h').write_text(STUB_ARDUINO); (tmp_path / 'EEPROM.h').write_text(STUB_EEPROM)
    for h in ('io.h', 'interrupt.h'): (tmp_path / 'avr' / h).write_text('#pragma once\n#include "../Arduino.h"\n')
    (tmp_path / 'smoke.cpp').write_text(SMOKE.replace('SKETCH', str(real.SKETCH / 'wlb_mega.ino')))
    exe = tmp_path / 'smoke'
    r = subprocess.run([CXX, '-std=c++11', '-Wall', '-Wextra', '-I', str(tmp_path), '-o', str(exe), str(tmp_path / 'smoke.cpp'),
                        str(real.SKETCH / 'protocol_core.cpp')], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-3000:]
    lines = [protocol.encode(dict(cmd='CLR', seq=1, home=True)), protocol.encode(dict(cmd='TT', seq=2, deg=10.0, ms=2000)),
             protocol.encode(dict(cmd='HB', seq=3))]
    r = subprocess.run([str(exe)] + [l.rstrip('\n') for l in lines], capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stdout


def test_sketch_compiles_with_arduino_cli(tmp_path):
    status, detail = real.compile_sketch(tmp_path)
    if status == 'SKIP': pytest.skip(detail)
    assert status == 'PASS', detail


# ------------------------------------------------------------------ MegaClient over SerialTransport, firmware core in real time
class PipeSerial:
    """pyserial stand-in over the pipes of `test_protocol_core --live` (the firmware core running in real time)"""

    def __init__(self, exe, grams=0.0):
        self.p = subprocess.Popen([str(exe), '--live', str(grams)], stdin=subprocess.PIPE, stdout=subprocess.PIPE, bufsize=0)
        self._buf = bytearray(); self._lock = threading.Lock()
        threading.Thread(target=self._reader, daemon=True).start()

    def _reader(self):
        while True:
            b = os.read(self.p.stdout.fileno(), 4096)
            if not b: return
            with self._lock: self._buf += b

    @property
    def in_waiting(self):
        with self._lock: return len(self._buf)

    def read(self, n=1):
        with self._lock: out = bytes(self._buf[:n]); del self._buf[:n]; return out

    def write(self, data):
        self.p.stdin.write(data); self.p.stdin.flush(); return len(data)

    def close(self):
        self.p.stdin.close(); self.p.wait(timeout=5)


@needs_cxx
@pytest.mark.skipif(os.name == 'nt', reason='--live mode needs POSIX select()')
def test_megaclient_over_serialtransport_against_the_firmware_core_in_real_time(fw_build):
    seen = {}

    def factory(**kw):
        seen.update(kw); return PipeSerial(fw_build['exe'], grams=12.5)

    t = real.SerialTransport('pipe', serial_factory=factory).open()
    assert seen['dtr'] is False and seen['rts'] is False and seen['baudrate'] == 250000
    mega = MegaClient(t, real.RealClock())
    try:
        r = mega.command('PING')
        assert r['ok'] and r['fw'].startswith('wlb-mega') and r['sim'] is False and r['pos'] == 'known'
        mega.command('STREAM', on=True); mega.take_samples(); time.sleep(1.0); n = len(mega.take_samples())
        assert 70 <= n <= 90, n                                          # 80 SPS, real time on a busy host
        mega.command('TARE'); assert abs(mega.read_mass(16)) < 0.2
        r = mega.motion('TT', done_timeout=5, deg=20.0, ms=1000); assert r['deg'] == 20.0
        r = mega.motion('AUG', done_timeout=5, rev=0.5, dir=1); assert abs(r['rev'] - 0.5) < 0.02 and r['stalls'] == 0
        with pytest.raises(MegaError) as e: mega.command('TT', deg=400.0, ms=1000)
        assert e.value.code == 'RANGE'
        mega.keepalive = False; s = mega.send('TT', deg=0.0, ms=2000); mega.wait(s, key=('ack',))
        time.sleep(0.8); mega._pump()
        assert [f['fault'] for f in mega.faults] == ['WDT'] and not any(m.get('done') for m in mega.replies.get(s, []))
        assert not [x for x in mega.log if x[0] == 'bad-line']
    finally:
        t.close()
