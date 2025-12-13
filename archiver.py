import struct
from typing import Dict, Optional, Callable

from bitops import BitWriter, BitReader
from huffman import CanonicalHuffman
from lz77 import LZ77Compressor


class Archiver:
    """Main archiver combining LZ77 and Canonical Huffman coding.

    :ivar VERSION: Format version of the encoder/decoder.
    :type VERSION: int
    :ivar lz77: LZ77 compressor instance.
    :type lz77: LZ77Compressor
    :ivar huffman: Canonical Huffman coder instance.
    :type huffman: CanonicalHuffman
    """

    VERSION = 1

    def __init__(self):
        """Initialize compressor and Huffman coder instances.

        :returns: None
        :rtype: None
        """
        self.lz77 = LZ77Compressor()
        self.huffman = CanonicalHuffman()

    def compress(
        self,
        data: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> bytes:
        """Compress raw ``data`` using LZ77 + Huffman coding.

        :param data: Input bytes to compress.
        :type data: bytes
        :param on_progress: Optional callback ``on_progress(done, total)`` to
                            report per-file progress based on input bytes
                            processed. It is called with values in range
                            ``0..len(data)``.
        :type on_progress: Optional[Callable[[int, int], None]]
        :returns: Compressed byte stream.
        For empty input returns header with size 0.
        :rtype: bytes
        """
        if not data:
            return struct.pack("<BI", self.VERSION, 0)

        tokens, freq = self.lz77.compress(data, on_progress=on_progress)

        self.huffman.build_from_frequencies(freq)

        output = BitWriter()

        output.write_bits(self.VERSION, 8)
        output.write_bits(len(data), 32)

        metadata = self.huffman.save_metadata()
        output.write_bits(len(metadata), 16)
        output.write_bytes(metadata)

        for distance, length, literal in tokens:
            if literal >= 0:
                code, code_len = self.huffman.encode_symbol(literal)
                output.write_bits(code, code_len)
            else:
                length_code = 256 + (length - self.lz77.MIN_MATCH)
                code, code_len = self.huffman.encode_symbol(length_code)
                output.write_bits(code, code_len)
                output.write_bits(distance - 1, 15)

        if on_progress is not None:
            try:
                on_progress(len(data), len(data))
            except Exception:
                pass

        return output.flush()

    def decompress(
        self,
        data: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> bytes:
        """Decompress data produced by ``compress``.

        :param data: Compressed byte stream.
        :type data: bytes
        :param on_progress: Optional callback ``on_progress(done, total)`` to
                            report per-file progress of recovered bytes.
        :type on_progress: Optional[Callable[[int, int], None]]
        :returns: Original uncompressed bytes.
        :rtype: bytes
        :raises ValueError: If the version is unsupported or
        if an invalid Huffman code is encountered.
        :raises EOFError: If the input data ends unexpectedly while
        reading bits.
        """
        reader = BitReader(data)

        version = reader.read_bits(8)
        if version != self.VERSION:
            raise ValueError(f"Unsupported version: {version}")

        orig_size = reader.read_bits(32)
        if orig_size == 0:
            return b""

        metadata_len = reader.read_bits(16)
        metadata = reader.read_bytes(metadata_len)
        self.huffman.load_metadata(metadata)

        decode_tree = self._build_decode_tree()

        tokens = []
        output_len = 0

        while output_len < orig_size:
            symbol = self._decode_symbol(reader, decode_tree)

            if symbol < 256:
                tokens.append((0, 0, symbol))
                output_len += 1
            else:
                length = symbol - 256 + self.lz77.MIN_MATCH
                distance = reader.read_bits(15) + 1
                tokens.append((distance, length, -1))
                output_len += length

            if on_progress is not None:
                try:
                    on_progress(min(output_len, orig_size), orig_size)
                except Exception:
                    pass

        return self.lz77.decompress(tokens)

    def _build_decode_tree(self) -> Dict:
        """Build a simple lookup table for canonical Huffman decoding.

        :returns: Mapping from ``(code, length)`` to symbol.
        :rtype: Dict[Tuple[int, int], int]
        """
        tree = {}
        for symbol in self.huffman.symbols:
            code, length = self.huffman.codes[symbol]
            tree[(code, length)] = symbol
        return tree

    @staticmethod
    def _decode_symbol(reader: BitReader, tree: Dict) -> int:
        """Decode the next symbol from a canonical Huffman tree.

        :param reader: Bit reader to consume bits from.
        :type reader: BitReader
        :param tree: Mapping from ``(code, length)`` to symbol.
        :type tree: Dict
        :returns: Decoded symbol value.
        :rtype: int
        :raises ValueError: If no valid code can be formed from the next bits.
        """
        code = 0
        for length in range(1, 26):
            bit = reader.read_bits(1)
            code = (code << 1) | bit
            key = (code, length)
            if key in tree:
                return tree[key]
        raise ValueError("Invalid Huffman code")
