from bench.hal import protocol


def test_roundtrip():
    msg = {"id": 7, "cmd": "carousel", "deg": 180.0, "ms": 4000}
    assert protocol.decode(protocol.encode(msg)) == msg


def test_junk_is_not_a_crash():
    assert protocol.decode(b"\xff\xfe not json\n") == {"junk": "�� not json"}
    assert protocol.decode(b"\n") is None


def test_validate_rejects_out_of_range_never_clamps():
    assert protocol.validate({"cmd": "stage", "deg": 170, "ms": 2500}) == "RANGE"
    assert protocol.validate({"cmd": "stage", "deg": 150, "ms": 2500}) is None
    assert protocol.validate({"cmd": "auger", "rev": 60}) == "RANGE"
    assert protocol.validate({"cmd": "carousel", "deg": 90, "ms": 100}) == "RANGE"
    assert protocol.validate({"cmd": "fly"}) == "UNKNOWN"
