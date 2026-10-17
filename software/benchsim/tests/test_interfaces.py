import pytest

from benchsim import protocol
from benchsim.bench import HardwareNotAllowed, make_bench
from benchsim.layout import load_params


def test_codec_round_trip_and_crc():
    line = protocol.encode(dict(cmd='TT', seq=7, deg=90.0, ms=4000))
    assert protocol.decode(line) == dict(cmd='TT', seq=7, deg=90.0, ms=4000)
    bad = line.replace('90.0', '91.0')
    with pytest.raises(protocol.ProtocolError) as e: protocol.decode(bad)
    assert e.value.code == 'CRC'


def test_validation_ranges():
    lim = protocol.Limits(load_params())
    with pytest.raises(protocol.ProtocolError) as e: protocol.validate(dict(cmd='ST', seq=1, deg=170.0, ms=3000), lim)
    assert e.value.code == 'RANGE'
    with pytest.raises(protocol.ProtocolError) as e: protocol.validate(dict(cmd='AUG', seq=1, rev=1.0, dir=0), lim)
    assert e.value.code == 'BADCMD'
    assert protocol.validate(dict(cmd='AUG', seq=1, rev=8.2, dir=-1), lim) == 'AUG'


def test_real_mode_needs_explicit_opt_in():
    with pytest.raises(HardwareNotAllowed): make_bench('real')


def test_exercise_all_checks_pass():
    from benchsim import exercise
    rows = exercise.run()
    assert all(r['ok'] for r in rows), [r for r in rows if not r['ok']]
