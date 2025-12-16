import pytest

from lz77 import LZ77Compressor


def test_lz77_roundtrip_small_text_and_freqs(progress_recorder):
    data = b"abracadabra abracadabra\n"
    lz = LZ77Compressor()
    on_prog, progress_calls = progress_recorder
    tokens, freqs = lz.compress(data, on_progress=on_prog)
    out = LZ77Compressor.decompress(tokens)
    assert out == data
    assert progress_calls and progress_calls[-1][0] == len(data)
    assert progress_calls[-1][1] == len(data)
    assert sum(freqs.values()) == len(tokens)


def test_lz77_empty_input():
    lz = LZ77Compressor()
    tokens, freqs = lz.compress(b"")
    assert tokens == []
    assert hasattr(freqs, "values") and sum(freqs.values()) == 0
    out = LZ77Compressor.decompress(tokens)
    assert out == b""


def test_lz77_decompress_invalid_distance_raises():
    tokens = [(0, 0, ord('A')), (5, 3, -1)]
    with pytest.raises(ValueError):
        _ = LZ77Compressor.decompress(tokens)
