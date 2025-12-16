import pytest

from bitops import BitWriter, BitReader


def test_bitwriter_write_bits_and_flush_basic():
    bw = BitWriter()
    bw.write_bits(0b1010, 4)
    bw.write_bits(0b11110000, 8)
    out = bw.flush()
    assert isinstance(out, (bytes, bytearray))
    assert len(out) == 2
    assert out[0] == 0b10101111
    assert out[1] == 0b00000000


def test_bitwriter_write_bytes_aligns():
    bw = BitWriter()
    bw.write_bits(0b1, 1)
    bw.write_bytes(b"AB")
    out = bw.flush()
    assert out[0] == 0b10000000
    assert out[1:] == b"AB"


def test_bitreader_read_bits_and_bytes_alignment():
    data = bytes([0b11001010, 0xFF, 0x00])
    br = BitReader(data)
    first3 = br.read_bits(3)
    assert first3 == 0b110
    next5 = br.read_bits(5)
    assert next5 == 0b01010
    b = br.read_bytes(2)
    assert b == bytes([0xFF, 0x00])


def test_bitreader_eoferror_on_insufficient_bits():
    br = BitReader(b"\xF0")
    with pytest.raises(EOFError):
        _ = br.read_bits(9)


def test_write_zero_bits_is_noop_and_flush_padding():
    bw = BitWriter()
    bw.write_bits(0xAA, 8)
    bw.write_bits(0, 0)
    out = bw.flush()
    assert out == bytes([0xAA])
