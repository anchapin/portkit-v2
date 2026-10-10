"""pack_icon.png for both packs (#115).

Bedrock loads a pack without an icon, but shows a placeholder in the pack list,
and Mojang's validator (mct CPACKICON) treats a missing one as an error. Every
loader lets a mod declare its own logo, so that is used when there is one:

    fabric.mod.json          "icon": "path" or {"<size>": "path", ...}
    quilt.mod.json           quilt_loader.metadata.icon, same two shapes
    META-INF/(neoforge.)mods.toml   logoFile, per [[mods]] entry or top level
    mcmod.info               logoFile
    pack.png                 the resource-pack convention, as a last resort

Bedrock wants a square icon of 2..256 pixels, a power of two. Such a PNG is
copied byte for byte; any other PNG is centred on a transparent square, which
keeps the whole logo rather than cropping a banner down to its middle, and
scaled down to the largest allowed size that fits. A mod that declares nothing, or whose
logo can't be read, gets a small generated icon (the second case is noted).
"""
from __future__ import annotations

import hashlib
import json
import tomllib

from . import png

ICON_NAME = "pack_icon.png"
_DEFAULT_SIZE = 64
# Decoding and scaling are pure Python; past this many pixels they would take
# minutes, so a bigger non-conforming logo falls back to the generated icon.
_MAX_DECODE_PIXELS = 1024 * 1024


def _pick(value) -> str | None:
    """A path out of an icon field: a string, or the largest of a size map."""
    if isinstance(value, str):
        return value or None
    if isinstance(value, dict):
        sized = []
        for size, path in value.items():
            if not isinstance(path, str) or not path:
                continue
            try:
                sized.append((int(size), path))
            except (TypeError, ValueError):
                sized.append((0, path))
        if sized:
            return max(sized)[1]
    return None


def declared_paths(metadata: dict[str, bytes]) -> list[str]:
    """Every icon path the mod declares, most authoritative first, then pack.png.

    Paths are jar-relative with any leading slash removed. Nothing here raises:
    unreadable metadata just declares nothing.
    """
    found: list[str] = []

    def add(path) -> None:
        if isinstance(path, str):
            path = path.strip().lstrip("/")
            if path and path not in found:
                found.append(path)

    for name in ("fabric.mod.json", "quilt.mod.json"):
        blob = metadata.get(name)
        if blob is None:
            continue
        try:
            # strict=False: Fabric's own parser accepts raw newlines inside
            # strings (betterend's description has them), so we do too.
            data = json.loads(blob, strict=False)
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if name == "quilt.mod.json":
            data = ((data.get("quilt_loader") or {}).get("metadata") or {})
        add(_pick(data.get("icon")))

    for name in ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"):
        blob = metadata.get(name)
        if blob is None:
            continue
        try:
            data = tomllib.loads(blob.decode("utf-8", "replace"))
        except tomllib.TOMLDecodeError:
            continue
        for mod in data.get("mods") or []:
            if isinstance(mod, dict):
                add(mod.get("logoFile"))
        add(data.get("logoFile"))

    blob = metadata.get("mcmod.info")
    if blob is not None:
        try:
            data = json.loads(blob)
        except (json.JSONDecodeError, UnicodeDecodeError):
            data = None
        entries = data.get("modList") if isinstance(data, dict) else data
        for entry in entries or []:
            if isinstance(entry, dict):
                add(entry.get("logoFile"))

    add("pack.png")
    return found


# mct CPACKICON: "pack_icon must be square with size 2, 4, 8, 16, 32, 64, 128,
# or 256".
_SIZES = (2, 4, 8, 16, 32, 64, 128, 256)


def target_size(side: int) -> int:
    """The largest allowed icon size not bigger than ``side`` (never upscale)."""
    fitting = [s for s in _SIZES if s <= side]
    return fitting[-1] if fitting else _SIZES[0]


def _resample_axis(src: list[float], length: int, count: int, stride_in: int, new: int) -> list[float]:
    """Area-average ``count`` lines of ``length`` RGBA pixels down to ``new``.

    Lines are laid out ``stride_in`` floats apart; the output is ``count`` lines
    of ``new`` pixels, packed. Each output pixel averages the source span it
    covers, partial pixels weighted by overlap.
    """
    scale = length / new
    spans = []
    for i in range(new):
        lo, hi = i * scale, (i + 1) * scale
        weights = []
        j = int(lo)
        while j < hi and j < length:
            w = min(hi, j + 1) - max(lo, j)
            if w > 0:
                weights.append((j, w / scale))
            j += 1
        spans.append(weights)
    out: list[float] = []
    for line in range(count):
        base = line * stride_in
        for weights in spans:
            acc = [0.0, 0.0, 0.0, 0.0]
            for j, w in weights:
                k = base + j * 4
                acc[0] += src[k] * w
                acc[1] += src[k + 1] * w
                acc[2] += src[k + 2] * w
                acc[3] += src[k + 3] * w
            out.extend(acc)
    return out


def _resize(side: int, pixels: bytes, new: int) -> bytes:
    """Square RGBA ``side`` x ``side`` down to ``new`` x ``new``, alpha-aware."""
    # Premultiply so transparent padding doesn't bleed black into the edges.
    flat: list[float] = []
    for i in range(0, len(pixels), 4):
        a = pixels[i + 3] / 255
        flat.extend((pixels[i] * a, pixels[i + 1] * a, pixels[i + 2] * a, pixels[i + 3]))
    rows = _resample_axis(flat, side, side, side * 4, new)  # side rows of new px
    # Transpose to resample the other axis with the same routine.
    cols = [0.0] * (new * side * 4)
    for y in range(side):
        for x in range(new):
            s, d = (y * new + x) * 4, (x * side + y) * 4
            cols[d : d + 4] = rows[s : s + 4]
    done = _resample_axis(cols, side, new, side * 4, new)  # new cols of new px
    out = bytearray(new * new * 4)
    for x in range(new):
        for y in range(new):
            s, d = (x * new + y) * 4, (y * new + x) * 4
            a = done[s + 3]
            if a <= 0:
                continue  # stays transparent black
            k = 255 / a
            out[d] = min(255, round(done[s] * k))
            out[d + 1] = min(255, round(done[s + 1] * k))
            out[d + 2] = min(255, round(done[s + 2] * k))
            out[d + 3] = min(255, round(a))
    return bytes(out)


def square(data: bytes) -> bytes | None:
    """An icon Bedrock accepts from this image, or None if it isn't a readable PNG
    (or is too big to rescale in pure Python).

    Bedrock (and mct) want a square of 2..256 pixels, a power of two. Such a
    PNG is copied byte for byte. Anything else is centred on a transparent
    square, keeping the whole logo rather than cropping a banner to its
    middle, and scaled down to the largest allowed size that fits.
    """
    size = png.dimensions(data)
    if size is None:
        return None
    width, height = size
    if width == height and width in _SIZES:
        return data
    if width * height > _MAX_DECODE_PIXELS:
        return None
    decoded = png.decode_rgba(data)
    if decoded is None:
        return None
    width, height, pixels = decoded
    side = max(width, height)
    left, top = (side - width) // 2, (side - height) // 2
    canvas = bytearray(side * side * 4)  # transparent black
    for y in range(height):
        start = ((top + y) * side + left) * 4
        canvas[start : start + width * 4] = pixels[y * width * 4 : (y + 1) * width * 4]
    new = target_size(side)
    body = bytes(canvas) if new == side else _resize(side, bytes(canvas), new)
    return png.encode_png(new, new, body)


def default_icon(namespace: str) -> bytes:
    """A small generated icon: a border and a centre tile in the mod's own colour.

    The colour comes from the namespace's hash, so two converted mods are told
    apart in the pack list and the same mod always gets the same icon. Stored
    deflate keeps the bytes identical on every zlib, for the golden fixtures.
    """
    digest = hashlib.sha256(namespace.encode("utf-8")).digest()
    base = bytes(64 + b % 128 for b in digest[:3])
    light = bytes(min(255, c + 80) for c in base)
    dark = bytes(c // 2 for c in base)
    palette = dark + base + light
    n = _DEFAULT_SIZE
    rows = bytearray()
    for y in range(n):
        for x in range(n):
            edge = min(x, y, n - 1 - x, n - 1 - y)
            rows.append(0 if edge < 4 else (2 if 20 <= edge else 1))
    return png.encode_png(n, n, bytes(rows), color=3, palette=palette, level=0)


def resolve(candidates: dict[str, bytes], namespace: str) -> tuple[bytes, str | None, str | None]:
    """(icon bytes, source path used or None, note or None).

    ``candidates`` maps each declared path that exists in the mod to its bytes,
    in declaration order.
    """
    tried: list[str] = []
    for path, blob in candidates.items():
        icon = square(blob)
        if icon is not None:
            return icon, path, None
        tried.append(path)
    # A mod with no icon is ordinary and the placeholder loses nothing, so only
    # a declared icon that could not be used is worth a note.
    note = (
        f"mod icon {', '.join(tried)} is not a PNG portkit can read; "
        "pack_icon.png is a generated placeholder"
    ) if tried else None
    return default_icon(namespace), None, note
