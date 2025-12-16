import pytest

from huffman import CanonicalHuffman
from bitops import BitWriter


def test_build_from_frequencies_empty():
    h = CanonicalHuffman()
    h.build_from_frequencies({})
    assert h.codes == {}
    assert h.encode_symbol(123) == (0, 1)


def test_build_single_symbol_and_encode():
    h = CanonicalHuffman()
    h.build_from_frequencies({65: 10})
    assert h.code_lengths == {65: 1}
    code, length = h.encode_symbol(65)
    assert length == 1
    assert isinstance(code, int)


def test_multi_symbol_roundtrip_metadata_and_codes_stable():
    freqs = {ord('A'): 5, ord('B'): 7, ord('C'): 2, 256: 3}
    h1 = CanonicalHuffman()
    h1.build_from_frequencies(freqs)
    meta = h1.save_metadata()

    h2 = CanonicalHuffman()
    consumed = h2.load_metadata(meta)
    assert consumed == len(meta)
    assert h1.code_lengths == h2.code_lengths
    assert h1.codes == h2.codes

    for s in h1.symbols:
        c1 = h1.encode_symbol(s)
        c2 = h2.encode_symbol(s)
        assert c1 == c2 and c1[1] > 0


def test_load_metadata_truncated_raises_eoferror():
    bw = BitWriter()
    bw.write_bits(1, 16)
    meta = bw.flush()

    h = CanonicalHuffman()
    with pytest.raises(EOFError):
        _ = h.load_metadata(meta)
