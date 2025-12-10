class BitWriter:
    """Bit-packing writer.

    Accumulates individual bits into bytes and buffers them until
    flushed.

    :ivar buffer: Internal byte buffer holding fully written bytes.
    :type buffer: bytearray
    :ivar bit_buffer: 8-bit scratch register for accumulating pending bits.
    :type bit_buffer: int
    :ivar bit_count: Number of valid bits currently stored in ``bit_buffer`` (0-7).
    :type bit_count: int
    """

    def __init__(self):
        """Initialize an empty bit writer.

        :returns: None
        :rtype: None
        """
        self.buffer = bytearray()
        self.bit_buffer = 0
        self.bit_count = 0

    def write_bits(self, value: int, nbits: int):
        """Write the lowest ``nbits`` of ``value`` to the buffer, MSB first.

        :param value: Integer whose bits will be written.
        :type value: int
        :param nbits: Number of bits from ``value`` to write (0-32 typical).
        :type nbits: int
        :returns: None
        :rtype: None
        """
        for i in range(nbits - 1, -1, -1):
            self.bit_buffer = (self.bit_buffer << 1) | ((value >> i) & 1)
            self.bit_count += 1
            if self.bit_count == 8:
                self.buffer.append(self.bit_buffer)
                self.bit_buffer = 0
                self.bit_count = 0

    def write_bytes(self, data: bytes):
        """Write raw bytes, aligning pending bits to the next byte boundary.

        If there are pending bits in ``bit_buffer``, they are left-shifted to
        fill the current byte and appended before writing ``data``.

        :param data: Byte sequence to append to the output.
        :type data: bytes
        :returns: None
        :rtype: None
        """
        if self.bit_count > 0:
            self.bit_buffer <<= (8 - self.bit_count)
            self.buffer.append(self.bit_buffer)
            self.bit_buffer = 0
            self.bit_count = 0
        self.buffer.extend(data)

    def flush(self) -> bytes:
        """Flush remaining bits (if any) and return the full byte buffer.

        Any partial byte in ``bit_buffer`` is padded with zeros to complete the
        byte before being appended.

        :returns: The accumulated bytes written so far.
        :rtype: bytes
        """
        if self.bit_count > 0:
            self.bit_buffer <<= (8 - self.bit_count)
            self.buffer.append(self.bit_buffer)
            self.bit_buffer = 0
            self.bit_count = 0
        return bytes(self.buffer)


class BitReader:
    """Efficient bit-packing reader.

    Reads arbitrary bit lengths from a bytes-like object.

    :ivar data: Input data to read bits/bytes from.
    :type data: bytes
    :ivar pos: Current position in ``data`` (byte index).
    :type pos: int
    :ivar bit_buffer: Scratch register holding the current source byte.
    :type bit_buffer: int
    :ivar bit_count: Number of unread bits remaining in ``bit_buffer`` (0-8).
    :type bit_count: int
    """

    def __init__(self, data: bytes):
        """Create a bit reader for the given input ``data``.

        :param data: Source data to read from.
        :type data: bytes
        :returns: None
        :rtype: None
        """
        self.data = data
        self.pos = 0
        self.bit_buffer = 0
        self.bit_count = 0

    def read_bits(self, nbits: int) -> int:
        """Read ``nbits`` bits from the stream and return them as an integer.

        Bits are returned MSB-first in the integer.

        :param nbits: Number of bits to read.
        :type nbits: int
        :returns: The integer value composed of the next ``nbits`` bits.
        :rtype: int
        :raises EOFError: If the end of data is reached before reading ``nbits``.
        """
        result = 0
        for _ in range(nbits):
            if self.bit_count == 0:
                if self.pos >= len(self.data):
                    raise EOFError("Unexpected end of data")
                self.bit_buffer = self.data[self.pos]
                self.pos += 1
                self.bit_count = 8
            result = (result << 1) | ((self.bit_buffer >> (self.bit_count - 1)) & 1)
            self.bit_count -= 1
        return result

    def read_bytes(self, nbytes: int) -> bytes:
        """Read ``nbytes`` raw bytes from the stream.

        Any pending bits are discarded (byte-aligns the stream) before reading.

        :param nbytes: Number of bytes to read.
        :type nbytes: int
        :returns: The next ``nbytes`` bytes (may be shorter only if source is shorter).
        :rtype: bytes
        """
        if self.bit_count > 0:
            self.bit_count = 0
        result = self.data[self.pos:self.pos + nbytes]
        self.pos += nbytes
        return result