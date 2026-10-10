"""pack_icon.png in both packs, from the mod's own logo when it declares one (#115)."""
import json
import struct
import zipfile
import zlib

from portkit import png
from portkit.icon import declared_paths, default_icon, resolve, square, target_size
from portkit.pipeline import convert
from portkit.validate import validate_tree

TEXTURE = b"\x89PNG\r\n\x1a\n"


def rgba_png(width, height, pixel=(200, 10, 20, 255)):
    return png.encode_png(width, height, bytes(pixel) * (width * height))


def palette_png(width, height, indices, palette, trns=b""):
    raw = b"".join(b"\x00" + bytes(indices[y * width:(y + 1) * width]) for y in range(height))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))

    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 3, 0, 0, 0))
    out += chunk(b"PLTE", palette)
    if trns:
        out += chunk(b"tRNS", trns)
    return out + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def mod_dir(tmp_path, metadata_name=None, metadata=b"", files=None):
    src = tmp_path / "src"
    block = src / "assets" / "examplemod" / "textures" / "block"
    block.mkdir(parents=True)
    (block / "stone.png").write_bytes(TEXTURE)
    if metadata_name:
        target = src / metadata_name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(metadata)
    for rel, blob in (files or {}).items():
        target = src / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(blob)
    return src


# --- where the icon is declared -------------------------------------------


def test_fabric_icon_string_and_size_map():
    assert declared_paths({"fabric.mod.json": b'{"icon": "assets/x/icon.png"}'})[0] == "assets/x/icon.png"
    sized = {"fabric.mod.json": json.dumps({"icon": {"16": "small.png", "128": "big.png"}}).encode()}
    assert declared_paths(sized)[0] == "big.png"


def test_fabric_json_with_raw_newlines_in_strings_still_declares_its_icon():
    blob = b'{"description": "line one\nline two", "icon": "assets/x/icon.png"}'
    assert declared_paths({"fabric.mod.json": blob})[0] == "assets/x/icon.png"


def test_quilt_icon():
    blob = json.dumps({"quilt_loader": {"metadata": {"icon": "q.png"}}}).encode()
    assert declared_paths({"quilt.mod.json": blob})[0] == "q.png"


def test_forge_and_neoforge_logo_file():
    forge = b'logoFile="top.png"\n[[mods]]\nmodId="a"\nlogoFile="logo.png"\n'
    assert declared_paths({"META-INF/mods.toml": forge})[:2] == ["logo.png", "top.png"]
    neo = b'[[mods]]\nmodId="a"\nlogoFile="neo.png"\n'
    assert declared_paths({"META-INF/neoforge.mods.toml": neo})[0] == "neo.png"


def test_mcmod_info_skips_empty_and_strips_leading_slash():
    blob = json.dumps([{"modid": "a", "logoFile": "/assets/a/logo.png"}]).encode()
    assert declared_paths({"mcmod.info": blob})[0] == "assets/a/logo.png"
    empty = json.dumps([{"modid": "a", "logoFile": ""}]).encode()
    assert declared_paths({"mcmod.info": empty}) == ["pack.png"]


def test_pack_png_is_the_last_resort_and_bad_metadata_declares_nothing():
    assert declared_paths({}) == ["pack.png"]
    assert declared_paths({"fabric.mod.json": b"{not json", "META-INF/mods.toml": b"[[["}) == ["pack.png"]


# --- making it square ------------------------------------------------------


def test_a_square_power_of_two_png_is_copied_byte_for_byte():
    icon = rgba_png(8, 8)
    assert square(icon) is icon


def test_a_banner_is_centred_on_a_transparent_square():
    out = square(rgba_png(8, 2))
    width, height, pixels = png.decode_rgba(out)
    assert (width, height) == (8, 8)

    def px(x, y):
        i = (y * 8 + x) * 4
        return tuple(pixels[i:i + 4])

    assert px(0, 0) == (0, 0, 0, 0)  # padding above
    assert px(0, 3) == (200, 10, 20, 255) and px(7, 4) == (200, 10, 20, 255)  # the logo, rows 3-4
    assert px(3, 7) == (0, 0, 0, 0)  # padding below


def test_sizes_bedrock_refuses_are_scaled_down_never_up():
    assert [target_size(n) for n in (1, 48, 120, 136, 256, 600)] == [2, 32, 64, 128, 256, 256]
    for side in (48, 600):
        out = square(rgba_png(side, side, (10, 200, 30, 255)))
        width, height, pixels = png.decode_rgba(out)
        assert width == height == target_size(side)
        # A flat colour stays that colour through the area average.
        assert set(zip(pixels[0::4], pixels[1::4], pixels[2::4], pixels[3::4])) == {(10, 200, 30, 255)}


def test_scaling_keeps_transparent_padding_from_darkening_the_logo():
    out = square(rgba_png(12, 6, (250, 250, 250, 255)))  # pads to 12, scales to 8
    width, _, pixels = png.decode_rgba(out)
    assert width == 8
    opaque = [tuple(pixels[i:i + 3]) for i in range(0, len(pixels), 4) if pixels[i + 3]]
    assert opaque and all(c == (250, 250, 250) for c in opaque)
    assert pixels[3] == 0  # the top-left corner is padding


def test_palette_images_decode_with_their_transparency():
    data = palette_png(2, 1, [0, 1], b"\x10\x20\x30\x40\x50\x60", trns=b"\x00")
    assert png.decode_rgba(data) == (2, 1, bytes([0x10, 0x20, 0x30, 0, 0x40, 0x50, 0x60, 255]))


def test_a_huge_non_conforming_logo_is_not_decoded():
    header = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + b"IHDR" + struct.pack(">IIBBBBB", 5000, 400, 8, 6, 0, 0, 0)
    assert square(header + b"\x00" * 8) is None


def test_not_a_png_is_refused():
    assert square(b"GIF89a....") is None
    assert png.decode_rgba(b"nope") is None


def test_unreadable_declared_icon_falls_back_with_a_note():
    icon, source, note = resolve({"logo.jpg": b"\xff\xd8\xff\xe0jpeg"}, "examplemod")
    assert icon == default_icon("examplemod") and source is None
    assert "logo.jpg" in note and "placeholder" in note


def test_the_default_icon_is_a_deterministic_square_png():
    first = default_icon("examplemod")
    assert first == default_icon("examplemod")
    assert first != default_icon("othermod")
    width, height, _ = png.decode_rgba(first)
    assert width == height == 64
    icon, source, note = resolve({}, "examplemod")
    assert icon == first and source is None and note is None


# --- end to end ------------------------------------------------------------


def test_a_fabric_icon_under_assets_ships_in_both_packs_and_leaves_the_residue(tmp_path):
    logo = rgba_png(16, 16)
    src = mod_dir(
        tmp_path,
        "fabric.mod.json",
        json.dumps({"id": "examplemod", "icon": "assets/examplemod/icon.png"}).encode(),
        {"assets/examplemod/icon.png": logo},
    )
    result = convert(src, tmp_path / "out")
    for pack in ("behavior_pack", "resource_pack"):
        if (result.tree / pack).is_dir():
            assert (result.tree / pack / "pack_icon.png").read_bytes() == logo
    assert (result.tree / "resource_pack" / "pack_icon.png").is_file()
    assert not any("icon.png" in u.source or u.source == "assets/examplemod/" for u in result.unhandled)
    assert not [f for f in result.report.findings if f.rule == "pack.icon"]


def test_a_forge_logo_at_the_jar_root_is_read_from_the_jar(tmp_path):
    logo = rgba_png(16, 4)
    jar = tmp_path / "mod.jar"
    with zipfile.ZipFile(jar, "w") as zf:
        zf.writestr("META-INF/mods.toml", 'modLoader="javafml"\n[[mods]]\nmodId="examplemod"\nlogoFile="logo.png"\n')
        zf.writestr("logo.png", logo)
        zf.writestr("assets/examplemod/textures/block/stone.png", TEXTURE)
    result = convert(jar, tmp_path / "out")
    icon = (result.tree / "resource_pack" / "pack_icon.png").read_bytes()
    assert png.dimensions(icon) == (16, 16)
    assert not any("pack_icon" in n or "icon" in n for n in result.notes)


def test_a_mod_with_no_icon_gets_the_generated_one(tmp_path):
    result = convert(mod_dir(tmp_path), tmp_path / "out")
    assert (result.tree / "resource_pack" / "pack_icon.png").read_bytes() == default_icon("examplemod")
    assert not any("icon" in n for n in result.notes)


def test_the_validator_warns_about_a_missing_icon(tmp_path):
    result = convert(mod_dir(tmp_path), tmp_path / "out")
    assert not [f for f in validate_tree(result.tree).findings if f.rule == "pack.icon"]
    (result.tree / "resource_pack" / "pack_icon.png").unlink()
    report = validate_tree(result.tree)
    found = [f for f in report.findings if f.rule == "pack.icon"]
    assert [f.path for f in found] == ["resource_pack/pack_icon.png"]
    assert found[0].severity == "warning" and report.ok


def test_the_validator_warns_about_an_icon_bedrock_refuses(tmp_path):
    result = convert(mod_dir(tmp_path), tmp_path / "out")
    (result.tree / "resource_pack" / "pack_icon.png").write_bytes(rgba_png(48, 48))
    found = [f for f in validate_tree(result.tree).findings if f.rule == "pack.icon"]
    assert len(found) == 1 and "48x48" in found[0].message and found[0].severity == "warning"
