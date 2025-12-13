from collections import defaultdict
from typing import Tuple, List, Counter, Dict, Optional, Callable


class LZ77Compressor:
    """Fast LZ77 compression with hash-based matching.

    :ivar MIN_MATCH: Minimum match length
    eligible for a (distance,length) token.
    :type MIN_MATCH: int
    :ivar MAX_MATCH: Maximum match length considered.
    :type MAX_MATCH: int
    :ivar WINDOW_SIZE: Sliding window size (maximum backward distance).
    :type WINDOW_SIZE: int
    :ivar MAX_HASH_CHAIN: Max number of candidates probed per position.
    :type MAX_HASH_CHAIN: int
    :ivar hash_table: Maps 3-byte hash to recent positions.
    :type hash_table: Dict[int, List[int]]
    """

    MIN_MATCH = 3
    MAX_MATCH = 258
    WINDOW_SIZE = 32768
    MAX_HASH_CHAIN = 32

    def __init__(self):
        """Initialize internal hash structures.

        :returns: None
        :rtype: None
        """
        self.hash_table: Dict[int, List[int]] = defaultdict(list)

    @staticmethod
    def _hash3(data: bytes, pos: int) -> int:
        """Compute a 3-byte rolling hash for ``data`` at ``pos``.

        :param data: Input data.
        :type data: bytes
        :param pos: Position to start hashing from.
        :type pos: int
        :returns: 24-bit hash value, or 0 if fewer than 3 bytes remain.
        :rtype: int
        """
        if pos + 3 > len(data):
            return 0
        return (
            (data[pos] << 16) | (data[pos + 1] << 8) | data[pos + 2]
        ) & 0xFFFFFF

    def _find_best_match(self, data: bytes, pos: int) -> Tuple[int, int]:
        """Find the best (distance, length) match starting at ``pos``.

        :param data: Input data to search in.
        :type data: bytes
        :param pos: Current position in ``data``.
        :type pos: int
        :returns: Tuple ``(distance, length)`` where 0-length means "no match".
        :rtype: Tuple[int, int]
        """
        if pos + self.MIN_MATCH > len(data):
            return 0, 0

        h = self._hash3(data, pos)
        best_len = self.MIN_MATCH - 1
        best_dist = 0
        max_len = min(self.MAX_MATCH, len(data) - pos)
        window_start = max(0, pos - self.WINDOW_SIZE)

        chain_count = 0
        for prev_pos in reversed(self.hash_table[h]):
            if prev_pos < window_start:
                break
            if chain_count >= self.MAX_HASH_CHAIN:
                break
            chain_count += 1

            if prev_pos >= pos:
                continue

            if data[prev_pos: prev_pos + 3] != data[pos: pos + 3]:
                continue

            length = 3
            while (
                length < max_len
                and data[prev_pos + length] == data[pos + length]
            ):
                length += 1

            if length > best_len:
                best_len = length
                best_dist = pos - prev_pos
                if best_len == max_len:
                    break

        if len(self.hash_table[h]) > 256:
            self.hash_table[h].pop(0)
        self.hash_table[h].append(pos)

        return best_dist, best_len if best_len >= self.MIN_MATCH else 0

    def compress(
        self,
        data: bytes,
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> Tuple[List[Tuple[int, int, int]], Counter]:
        """Compress raw data into LZ77 tokens and symbol frequencies.

        Tokens are either literals or matches:
        - Literal: ``(0, 0, literal_byte)``
        - Match: ``(distance, length, -1)``

        :param data: Uncompressed input bytes.
        :type data: bytes
        :param on_progress: Optional callback ``on_progress(pos, total)``
        invoked periodically with the current processed position
        and total input size.
        :type on_progress: Optional[Callable[[int, int], None]]
        :returns: A pair ``(tokens, frequencies)`` where ``tokens`` is a list
        of triples and ``frequencies`` is a Counter used for Huffman coding.
        :rtype: Tuple[List[Tuple[int, int, int]], Counter]
        """
        self.hash_table = defaultdict(list)
        tokens = []
        freq_counter = Counter()
        pos = 0
        total = len(data)

        while pos < len(data):
            distance, length = self._find_best_match(data, pos)

            if length >= self.MIN_MATCH:
                tokens.append((distance, length, -1))
                freq_counter[256 + (length - self.MIN_MATCH)] += 1
                pos += length
            else:
                byte_val = data[pos]
                tokens.append((0, 0, byte_val))
                freq_counter[byte_val] += 1
                pos += 1

            if on_progress is not None:
                on_progress(pos, total)

        return tokens, freq_counter

    @staticmethod
    def decompress(tokens: List[Tuple[int, int, int]]) -> bytes:
        """Decompress a sequence of LZ77 tokens into raw bytes.

        :param tokens: Token stream produced by ``compress``.
        :type tokens: List[Tuple[int, int, int]]
        :returns: Decompressed data.
        :rtype: bytes
        :raises ValueError: If a match token has an invalid distance.
        """
        output = bytearray()

        for distance, length, literal in tokens:
            if literal >= 0:
                output.append(literal)
            else:
                if distance <= 0 or distance > len(output):
                    raise ValueError(
                        f"Invalid LZ77 distance {distance}"
                        f"at output position {len(output)}"
                    )
                match_pos = len(output) - distance
                for _ in range(length):
                    output.append(output[match_pos])
                    match_pos += 1

        return bytes(output)
