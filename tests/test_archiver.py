import struct
import pytest

from archiver import Archiver
from bitops import BitReader


def test_archiver_roundtrip_with_progress(progress_recorder):
    data = (b"The quick brown fox jumps over the lazy dog. " * 5)
    arch = Archiver()
    on_prog, calls = progress_recorder
    comp = arch.compress(data, on_progress=on_prog)
    assert isinstance(comp, (bytes, bytearray)) and len(comp) > 0

    out = arch.decompress(comp, on_progress=on_prog)
    assert out == data
    assert any(d == len(data) and t == len(data) for d, t in calls)


def test_archiver_empty_input():
    arch = Archiver()
    comp = arch.compress(b"")
    assert len(comp) == 5
    out = arch.decompress(comp)
    assert out == b""


def test_archiver_decompress_wrong_version_raises():
    arch = Archiver()
    bad = struct.pack("<BI", 99, 0)
    with pytest.raises(ValueError):
        _ = arch.decompress(bad)


def test_decode_symbol_invalid_code_raises():
    reader = BitReader(b"\x00\x00\x00\x00")
    tree = {}
    with pytest.raises(ValueError):
        _ = Archiver._decode_symbol(reader, tree)
