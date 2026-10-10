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


def _rows(raw: bytes, width: int, height: int, bits_per_pixel: int) -> list[bytes]:
    """Unfiltered scanlines; ``bits_per_pixel`` may be below 8 (packed pixels)."""
    bpp = max(1, bits_per_pixel // 8)
    stride = (width * bits_per_pixel + 7) // 8
    flat = _unfilter_stride(raw, stride, height, bpp)
    return [flat[y * stride : (y + 1) * stride] for y in range(height)]


def _unfilter_stride(raw: bytes, stride: int, height: int, bpp: int) -> bytes:
    # _unfilter works in whole pixels; packed formats have a byte stride that
    # is not width * bpp, so wrap it with a width that gives the right stride.
    if stride % bpp:
        raise ValueError("stride is not a whole number of filter units")
    return _unfilter(raw, stride // bpp, height, bpp)


def decode_rgba(data: bytes) -> tuple[int, int, bytes] | None:
    """(width, height, RGBA bytes) for a non-interlaced PNG, or None if unread.

    Every colour type and bit depth is accepted (16-bit samples keep their high
    byte). Interlaced images are not: none of the icons in the corpus is one,
    and the caller falls back to a generated icon when this returns None.
    """
    if not data.startswith(_SIGNATURE):
        return None
    header, palette, trns = None, b"", b""
    idat = bytearray()
    for kind, body in _chunks(data):
        if kind == b"IHDR":
            header = struct.unpack(">IIBBBBB", body[:13])
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
    if header is None:
        return None
    width, height, depth, color, _, _, interlace = header
    if interlace != 0 or color not in _CHANNELS or width == 0 or height == 0:
        return None
    channels = _CHANNELS[color]
    try:
        rows = _rows(zlib.decompress(bytes(idat)), width, height, channels * depth)
    except (zlib.error, IndexError, ValueError):
        return None

    def samples(row: bytes) -> list[int]:
        if depth == 8:
            return list(row)
        if depth == 16:
            return list(row[0::2])
        per = 8 // depth
        mask = (1 << depth) - 1
        out = []
        for byte in row:
            for k in range(per):
                out.append((byte >> (8 - depth * (k + 1))) & mask)
        return out

    scale = 255 // ((1 << depth) - 1) if depth < 8 else 1
    out = bytearray()
    for row in rows:
        values = samples(row)[: width * channels]
        if len(values) < width * channels:
            return None
        for x in range(width):
            px = values[x * channels : (x + 1) * channels]
            if color == 3:
                i = px[0]
                if 3 * i + 2 >= len(palette):
                    return None
                r, g, b = palette[3 * i : 3 * i + 3]
                a = trns[i] if i < len(trns) else 255
            elif color == 0:
                r = g = b = px[0] * scale
                a = 255
            elif color == 4:
                r = g = b = px[0] * scale
                a = px[1] * scale
            elif color == 2:
                r, g, b = (v * scale for v in px)
                a = 255
            else:
                r, g, b, a = (v * scale for v in px)
            out += bytes((r, g, b, a))
    return width, height, bytes(out)


def _chunk(kind: bytes, body: bytes) -> bytes:
    crc = zlib.crc32(kind + body) & 0xFFFFFFFF
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)


def encode_png(
    width: int,
    height: int,
    pixels: bytes,
    *,
    color: int = 6,
    palette: bytes = b"",
    level: int = 9,
) -> bytes:
    """A minimal PNG: 8-bit RGBA (color 6), RGB (2) or palette (3), filter 0.

    ``level=0`` writes stored deflate blocks, which every zlib produces byte for
    byte the same, so a generated file can sit in a golden fixture.
    """
    channels = {6: 4, 2: 3, 3: 1}[color]
    stride = width * channels
    raw = b"".join(b"\x00" + pixels[y * stride : (y + 1) * stride] for y in range(height))
    body = _SIGNATURE + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
    if color == 3:
        body += _chunk(b"PLTE", palette)
    body += _chunk(b"IDAT", zlib.compress(raw, level))
    return body + _chunk(b"IEND", b"")


def dimensions(data: bytes) -> tuple[int, int] | None:
    """(width, height) from the IHDR, or None if this is not a PNG."""
    if not data.startswith(_SIGNATURE) or len(data) < 24 or data[12:16] != b"IHDR":
        return None
    return struct.unpack(">II", data[16:24])
