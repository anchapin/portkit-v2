"""The one PNG question the block converter asks: are there holes?"""
import struct
import zlib

from portkit import png


def _png(pixels: list[tuple[int, int, int, int]], width: int, filt: int = 0) -> bytes:
    rows = [pixels[i : i + width] for i in range(0, len(pixels), width)]
    raw = b"".join(bytes([filt]) + b"".join(bytes(p) for p in row) for row in rows)

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    header = struct.pack(">IIBBBBB", width, len(rows), 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def test_an_opaque_texture_has_no_holes():
    assert png.has_transparency(_png([(10, 20, 30, 255)] * 4, 2)) is False


def test_one_clear_pixel_is_a_hole():
    assert png.has_transparency(_png([(0, 0, 0, 255)] * 3 + [(0, 0, 0, 0)], 2)) is True


def test_a_broken_file_is_unread_not_guessed():
    assert png.has_transparency(b"not a png") is None
