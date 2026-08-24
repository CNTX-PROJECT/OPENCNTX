from __future__ import annotations

import argparse
import binascii
import hashlib
import struct
import tempfile
import zlib
from pathlib import Path
from xml.etree import ElementTree


ROOT = Path(__file__).resolve().parents[1]
BRAND = ROOT / "assets" / "brand"
AA = 4

SVG_PATHS = (
    "assets/brand/opencntx-avatar.svg",
    "assets/brand/opencntx-social-preview.svg",
    "assets/brand/opencntx-symbol-dark.svg",
    "assets/brand/opencntx-symbol-light.svg",
    "assets/brand/opencntx-wordmark-dark.svg",
    "assets/brand/opencntx-wordmark-light.svg",
)

GENERATED_PNG_JOBS = (
    ("opencntx-symbol-light.svg", "opencntx-icon-32.png", 32, 32),
    ("opencntx-symbol-light.svg", "opencntx-icon-128.png", 128, 128),
    ("opencntx-avatar.svg", "opencntx-avatar-512.png", 512, 512),
)

STATIC_PNG_PATHS = ("assets/brand/opencntx-social-preview-1280x640.png",)
PNG_PATHS = tuple(
    f"assets/brand/{job[1]}" for job in GENERATED_PNG_JOBS
) + STATIC_PNG_PATHS
HASHED_PATHS = tuple(sorted(SVG_PATHS + PNG_PATHS))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _number(value: str) -> float:
    return float(value)


def _color(value: str) -> tuple[int, int, int, int]:
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"unsupported fill: {value!r}")
    return (
        int(value[1:3], 16),
        int(value[3:5], 16),
        int(value[5:7], 16),
        255,
    )


def _shapes(element: ElementTree.Element, inherited_fill: str | None = None):
    name = _local_name(element.tag)
    fill = element.attrib.get("fill", inherited_fill)
    if name in {"svg", "g"}:
        for child in element:
            yield from _shapes(child, fill)
        return
    if name in {"title", "desc"}:
        return
    if name not in {"rect", "polygon", "circle", "ellipse"}:
        raise ValueError(f"unsupported SVG element: {name}")
    if fill is None:
        raise ValueError(f"missing fill on {name}")
    yield name, element.attrib, _color(fill)


def _set_pixel(canvas: bytearray, width: int, x: int, y: int, color) -> None:
    offset = (y * width + x) * 4
    canvas[offset : offset + 4] = bytes(color)


def _draw_rect(canvas, width, height, attrs, color, sx, sy) -> None:
    x0 = int(round(_number(attrs["x"]) * sx))
    y0 = int(round(_number(attrs["y"]) * sy))
    x1 = int(round((_number(attrs["x"]) + _number(attrs["width"])) * sx))
    y1 = int(round((_number(attrs["y"]) + _number(attrs["height"])) * sy))
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = min(width, x1), min(height, y1)
    row = bytes(color) * max(0, x1 - x0)
    for y in range(y0, y1):
        start = (y * width + x0) * 4
        canvas[start : start + len(row)] = row


def _inside_polygon(px: float, py: float, points) -> bool:
    inside = False
    previous_x, previous_y = points[-1]
    for current_x, current_y in points:
        crosses = (current_y > py) != (previous_y > py)
        if crosses:
            boundary_x = (
                (previous_x - current_x)
                * (py - current_y)
                / (previous_y - current_y)
                + current_x
            )
            if px < boundary_x:
                inside = not inside
        previous_x, previous_y = current_x, current_y
    return inside


def _draw_polygon(canvas, width, height, attrs, color, sx, sy) -> None:
    points = []
    for pair in attrs["points"].split():
        x, y = pair.split(",")
        points.append((_number(x) * sx, _number(y) * sy))
    min_x = max(0, int(min(point[0] for point in points)))
    max_x = min(width, int(max(point[0] for point in points)) + 1)
    min_y = max(0, int(min(point[1] for point in points)))
    max_y = min(height, int(max(point[1] for point in points)) + 1)
    for y in range(min_y, max_y):
        py = y + 0.5
        for x in range(min_x, max_x):
            if _inside_polygon(x + 0.5, py, points):
                _set_pixel(canvas, width, x, y, color)


def _draw_circle(canvas, width, height, attrs, color, sx, sy) -> None:
    cx = _number(attrs["cx"]) * sx
    cy = _number(attrs["cy"]) * sy
    rx = _number(attrs["r"]) * sx
    ry = _number(attrs["r"]) * sy
    min_x = max(0, int(cx - rx))
    max_x = min(width, int(cx + rx) + 1)
    min_y = max(0, int(cy - ry))
    max_y = min(height, int(cy + ry) + 1)
    for y in range(min_y, max_y):
        dy = ((y + 0.5) - cy) / ry
        for x in range(min_x, max_x):
            dx = ((x + 0.5) - cx) / rx
            if dx * dx + dy * dy <= 1.0:
                _set_pixel(canvas, width, x, y, color)


def _draw_ellipse(canvas, width, height, attrs, color, sx, sy) -> None:
    cx = _number(attrs["cx"]) * sx
    cy = _number(attrs["cy"]) * sy
    rx = _number(attrs["rx"]) * sx
    ry = _number(attrs["ry"]) * sy
    min_x = max(0, int(cx - rx))
    max_x = min(width, int(cx + rx) + 1)
    min_y = max(0, int(cy - ry))
    max_y = min(height, int(cy + ry) + 1)
    for y in range(min_y, max_y):
        dy = ((y + 0.5) - cy) / ry
        for x in range(min_x, max_x):
            dx = ((x + 0.5) - cx) / rx
            if dx * dx + dy * dy <= 1.0:
                _set_pixel(canvas, width, x, y, color)


def _downsample(canvas: bytearray, source_width: int, width: int, height: int) -> bytes:
    output = bytearray(width * height * 4)
    samples = AA * AA
    for y in range(height):
        for x in range(width):
            totals = [0, 0, 0, 0]
            for dy in range(AA):
                for dx in range(AA):
                    offset = (((y * AA + dy) * source_width) + x * AA + dx) * 4
                    alpha = canvas[offset + 3]
                    totals[0] += canvas[offset] * alpha
                    totals[1] += canvas[offset + 1] * alpha
                    totals[2] += canvas[offset + 2] * alpha
                    totals[3] += alpha
            alpha = (totals[3] + samples // 2) // samples
            target = (y * width + x) * 4
            if totals[3]:
                output[target] = (totals[0] + totals[3] // 2) // totals[3]
                output[target + 1] = (totals[1] + totals[3] // 2) // totals[3]
                output[target + 2] = (totals[2] + totals[3] // 2) // totals[3]
            output[target + 3] = alpha
    return bytes(output)


def _fixed_zlib(data: bytes) -> bytes:
    compressor = zlib.compressobj(
        level=9,
        method=zlib.DEFLATED,
        wbits=15,
        memLevel=9,
        strategy=zlib.Z_FIXED,
    )
    return compressor.compress(data) + compressor.flush(zlib.Z_FINISH)


def _chunk(name: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + name
        + data
        + struct.pack(">I", binascii.crc32(name + data) & 0xFFFFFFFF)
    )


def _png(width: int, height: int, rgba: bytes) -> bytes:
    rows = bytearray()
    stride = width * 4
    for y in range(height):
        rows.append(0)
        rows.extend(rgba[y * stride : (y + 1) * stride])
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + _chunk(b"IDAT", _fixed_zlib(bytes(rows)))
        + _chunk(b"IEND", b"")
    )


def _png_pixels(content: bytes) -> tuple[bytes, bytes]:
    if not content.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("invalid PNG signature")
    offset = 8
    header: bytes | None = None
    payloads = []
    while offset < len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        name = content[offset + 4 : offset + 8]
        payload = content[offset + 8 : offset + 8 + length]
        checksum = struct.unpack(">I", content[offset + 8 + length : offset + 12 + length])[0]
        if checksum != (binascii.crc32(name + payload) & 0xFFFFFFFF):
            raise ValueError("invalid PNG chunk checksum")
        if name == b"IHDR":
            header = payload
        elif name == b"IDAT":
            payloads.append(payload)
        offset += 12 + length
        if name == b"IEND":
            break
    if header is None or not payloads or offset != len(content):
        raise ValueError("incomplete PNG")
    return header, zlib.decompress(b"".join(payloads))


def render(svg_path: Path, output_path: Path, width: int, height: int) -> None:
    root = ElementTree.fromstring(svg_path.read_bytes())
    view_box = tuple(_number(value) for value in root.attrib["viewBox"].split())
    if view_box[:2] != (0.0, 0.0):
        raise ValueError("viewBox must start at 0 0")
    source_width = width * AA
    source_height = height * AA
    sx = source_width / view_box[2]
    sy = source_height / view_box[3]
    canvas = bytearray(source_width * source_height * 4)
    for name, attrs, color in _shapes(root):
        if name == "rect":
            _draw_rect(canvas, source_width, source_height, attrs, color, sx, sy)
        elif name == "polygon":
            _draw_polygon(canvas, source_width, source_height, attrs, color, sx, sy)
        elif name == "circle":
            _draw_circle(canvas, source_width, source_height, attrs, color, sx, sy)
        else:
            _draw_ellipse(canvas, source_width, source_height, attrs, color, sx, sy)
    rgba = _downsample(canvas, source_width, width, height)
    output_path.write_bytes(_png(width, height, rgba))


def _manifest_bytes(png_root: Path | None = None) -> bytes:
    lines = []
    for relative in HASHED_PATHS:
        path = ROOT / relative
        if png_root is not None and relative.endswith(".png"):
            generated = png_root / Path(relative).name
            if generated.is_file():
                path = generated
        data = path.read_bytes()
        if relative.endswith(".svg"):
            data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest = hashlib.sha256(data).hexdigest()
        lines.append(f"{digest}  {relative}")
    return " | ".join(lines).encode("ascii")


def write_assets() -> None:
    BRAND.mkdir(parents=True, exist_ok=True)
    for source, output, width, height in GENERATED_PNG_JOBS:
        render(BRAND / source, BRAND / output, width, height)
    (BRAND / "SHA256SUMS").write_bytes(_manifest_bytes())


def check_assets() -> None:
    with tempfile.TemporaryDirectory(prefix="opencntx-brand-") as directory:
        target = Path(directory)
        for source, output, width, height in GENERATED_PNG_JOBS:
            generated = target / output
            render(BRAND / source, generated, width, height)
            expected = BRAND / output
            if _png_pixels(generated.read_bytes()) != _png_pixels(expected.read_bytes()):
                raise SystemExit(f"brand derivative drift: {output}")
        expected_manifest = _manifest_bytes()
        if expected_manifest != (BRAND / "SHA256SUMS").read_bytes():
            raise SystemExit("brand hash manifest drift")
    print("BRAND_ASSETS_OK")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Render deterministic shape-only OPENCNTX PNGs and verify every "
            "committed brand asset."
        )
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write PNGs and SHA256SUMS")
    mode.add_argument("--check", action="store_true", help="verify committed derivatives")
    args = parser.parse_args()
    if args.write:
        write_assets()
    else:
        check_assets()


if __name__ == "__main__":
    main()
