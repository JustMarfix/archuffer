import heapq
from typing import Tuple, List, Dict
from bitops import BitWriter, BitReader


class HuffmanNode:
    """Node for a standard binary Huffman tree.

    :ivar symbol: The symbol (e.g., literal byte or length code) stored at a leaf; ``None`` for internal nodes.
    :type symbol: int | None
    :ivar freq: Frequency (weight) of the subtree rooted at this node.
    :type freq: int
    :ivar left: Left child node.
    :type left: HuffmanNode | None
    :ivar right: Right child node.
    :type right: HuffmanNode | None
    """

    def __init__(self, symbol=None, freq=0, left=None, right=None):
        """Create a Huffman node.

        :param symbol: Symbol value for leaf nodes; ``None`` for internal nodes.
        :type symbol: int | None
        :param int freq: Frequency (weight) associated with this node.
        :param left: Left child node, if any.
        :type left: HuffmanNode|None
        :param right: Right child node, if any.
        :type right: HuffmanNode|None
        :returns: None
        :rtype: None
        """
        self.symbol = symbol
        self.freq = freq
        self.left = left
        self.right = right

    def __lt__(self, other):
        """Order nodes by frequency (for priority queues).

        :param other: Another node to compare with.
        :type other: HuffmanNode
        :returns: ``True`` if this node's frequency is less than ``other``.
        :rtype: bool
        """
        return self.freq < other.freq


class CanonicalHuffman:
    """Canonical Huffman encoder/decoder.

    Maintains code lengths and canonical codes for a set of symbols.

    :ivar code_lengths: Mapping from symbol to code length (in bits).
    :type code_lengths: Dict[int, int]
    :ivar codes: Mapping from symbol to a tuple ``(code, length)``.
    :type codes: Dict[int, Tuple[int, int]]
    :ivar decode_table: Optional mapping reserved for decoding structures (not all methods use it).
    :type decode_table: Dict[int, int]
    :ivar symbols: Sorted list of symbols with defined codes.
    :type symbols: List[int]
    """

    def __init__(self):
        """Initialize empty canonical Huffman structures.

        :returns: None
        :rtype: None
        """
        self.code_lengths: Dict[int, int] = {}
        self.codes: Dict[int, Tuple[int, int]] = {}
        self.decode_table: Dict[int, int] = {}
        self.symbols: List[int] = []

    def build_from_frequencies(self, frequencies: Dict[int, int]):
        """Build canonical Huffman codes from a symbol frequency table.

        :param frequencies: Mapping from symbol to observed frequency.
        :type frequencies: Dict[int, int]
        :returns: None
        :rtype: None
        """
        self.code_lengths = {}
        self.codes = {}
        self.symbols = []

        if not frequencies:
            return

        if len(frequencies) == 1:
            symbol = next(iter(frequencies.keys()))
            self.code_lengths = {symbol: 1}
            self.symbols = [symbol]
            self._generate_canonical_codes()
            return

        heap = [HuffmanNode(symbol=sym, freq=freq) for sym, freq in frequencies.items()]
        heapq.heapify(heap)

        while len(heap) > 1:
            left = heapq.heappop(heap)
            right = heapq.heappop(heap)
            merged = HuffmanNode(freq=left.freq + right.freq, left=left, right=right)
            heapq.heappush(heap, merged)

        root = heap[0]
        self._get_code_lengths(root, 0)
        self._generate_canonical_codes()

    def _get_code_lengths(self, node: HuffmanNode, depth: int):
        """Populate ``code_lengths`` by traversing a Huffman tree.

        :param node: Current node in the Huffman tree.
        :type node: HuffmanNode
        :param depth: Current depth (code length so far).
        :type depth: int
        :returns: None
        :rtype: None
        """
        if node is None:
            return

        if node.left is None and node.right is None:
            self.code_lengths[node.symbol] = max(1, depth)
        else:
            self._get_code_lengths(node.left, depth + 1)
            self._get_code_lengths(node.right, depth + 1)

    def _generate_canonical_codes(self):
        """Generate canonical Huffman codes from ``code_lengths``.

        :returns: None
        :rtype: None
        """
        self.codes = {}
        self.symbols = sorted(self.code_lengths.keys())

        if not self.symbols:
            return

        code = 0
        prev_length = 0

        for symbol in sorted(self.symbols, key=lambda s: (self.code_lengths[s], s)):
            length = self.code_lengths[symbol]
            code <<= (length - prev_length)
            self.codes[symbol] = (code, length)
            code += 1
            prev_length = length

    def encode_symbol(self, symbol: int) -> Tuple[int, int]:
        """Get the canonical Huffman code for a symbol.

        :param symbol: Symbol to encode.
        :type symbol: int
        :returns: Tuple ``(code, length)``. If ``symbol`` is unknown, returns ``(0, 1)``.
        :rtype: Tuple[int, int]
        """
        return self.codes.get(symbol, (0, 1))

    def save_metadata(self) -> bytes:
        """Serialize code lengths for later reconstruction.

        The format stores the number of symbols (16 bits), and for each symbol
        its value (9 bits) followed by its code length (5 bits).

        :returns: Serialized metadata bytes.
        :rtype: bytes
        """
        data = BitWriter()
        data.write_bits(len(self.symbols), 16)
        for symbol in sorted(self.symbols):
            data.write_bits(symbol, 9)
            data.write_bits(self.code_lengths[symbol], 5)
        return data.flush()

    def load_metadata(self, data: bytes):
        """Load code lengths from serialized metadata and regenerate codes.

        :param data: Serialized metadata produced by :meth:`save_metadata`.
        :type data: bytes
        :returns: Number of bytes consumed from ``data`` while reading metadata.
        :rtype: int
        :raises EOFError: If the metadata is truncated.
        """
        reader = BitReader(data)
        num_symbols = reader.read_bits(16)
        self.code_lengths = {}
        for _ in range(num_symbols):
            symbol = reader.read_bits(9)
            length = reader.read_bits(5)
            self.code_lengths[symbol] = length
        self.symbols = list(self.code_lengths.keys())
        self._generate_canonical_codes()
        return reader.pos
