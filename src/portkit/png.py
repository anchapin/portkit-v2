"""Just enough PNG reading to ask one question: does any pixel see through?

Java decides cutout rendering in mod code, which we never run, so the texture
itself is the evidence: a face whose texture has see-through pixels needs
Bedrock's alpha_test, or the holes render as solid black. Stdlib only.
"""

import struct
import zlib

_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def _chunks(data: bytes):
    pos = len(_SIGNATURE)
    while pos + 8 <= len(data):
        (length,) = struct.unpack(">I", data[pos : pos + 4])
        kind = data[pos + 4 : pos + 8]
        yield kind, data[pos + 8 : pos + 8 + length]
        pos += 12 + length


def _unfilter(raw: bytes, width: int, height: int, bpp: int) -> bytes:
    stride = width * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for _ in range(height):
        kind = raw[pos]
        line = bytearray(raw[pos + 1 : pos + 1 + stride])
        pos += 1 + stride
        for i in range(stride):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + a) & 0xFF
            elif kind == 2:
                line[i] = (line[i] + b) & 0xFF
            elif kind == 3:
                line[i] = (line[i] + ((a + b) >> 1)) & 0xFF
            elif kind == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pred = a if pa <= pb and pa <= pc else (b if pb <= pc else c)
                line[i] = (line[i] + pred) & 0xFF
        out += line
        prev = line
    return bytes(out)


def has_transparency(data: bytes) -> bool | None:
    """True if some pixel is not fully opaque, False if none is, None if unread."""
    if not data.startswith(_SIGNATURE):
        return None
    header = None
    idat = bytearray()
    trns = False
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"tRNS":
            trns = True
        elif kind == b"IDAT":
            idat += body
    if header is None:
        return None
    width, height, depth, color, _, _, interlace = header
    if trns:
        return True
    if color not in (4, 6):
        return False
    if depth != 8 or interlace != 0:
        return None
    bpp = _CHANNELS[color]
    try:
        pixels = _unfilter(zlib.decompress(bytes(idat)), width, height, bpp)
    except (zlib.error, IndexError):
        return None
    return any(pixels[i] != 255 for i in range(bpp - 1, len(pixels), bpp))
