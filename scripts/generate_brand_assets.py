#!/usr/bin/env python3
"""Generate the Kestrel brand mark as SVG plus the raster icon set.

The Kestrel logo is a separate visual trademark (TRADEMARK.md section 5) and
cannot be redistributed by a fork, so every icon and the inline SVG in
web/src/components/Logo.tsx had to be replaced.

The mark is defined once here as a set of polygons in a 512x512 box, and both
the SVG and the PNG/ICO files are emitted from that same definition, so they
can never drift apart. Regenerate with:

    python3 scripts/generate_brand_assets.py

This is a placeholder: a clean, legible silhouette of a hovering kestrel, not a
designed identity. Replace it with real artwork when you have some -- keep the
filenames and this script's output paths and nothing else needs to change.
"""

from __future__ import annotations

import pathlib
import struct
import zlib

import numpy as np

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
SIZE = 512


def _bezier(points: list[tuple[float, float]], steps: int = 60) -> list[tuple[float, float]]:
    """Sample a Bezier curve of arbitrary degree (de Casteljau)."""
    pts = np.array(points, dtype=float)
    out = []
    for i in range(steps + 1):
        t = i / steps
        cur = pts.copy()
        while len(cur) > 1:
            cur = (1 - t) * cur[:-1] + t * cur[1:]
        out.append((float(cur[0][0]), float(cur[0][1])))
    return out


def kestrel_polygons() -> list[list[tuple[float, float]]]:
    """A kestrel seen from below: swept wings, long fanned tail.

    Three things make this read as a falcon rather than a stick figure, and all
    three were got wrong first: the wing has to be *widest where it meets the
    body* and taper to the tip (not pinch at the shoulder), the head has to
    overlap the body rather than float above it, and the tail has to stay one
    solid mass (a deep notch reads as legs). Kept as solid shapes so it
    survives being drawn at 16px.
    """
    # right wing: broad at the shoulder, tapering to a swept point
    leading = _bezier([(260, 138), (340, 116), (424, 108), (492, 112)])
    trailing = _bezier([(492, 112), (426, 178), (350, 236), (276, 286)])
    wing = leading + trailing + [(262, 214)]
    wing_left = [(512 - x, y) for x, y in reversed(wing)]

    # body and head as one mass: rounded crown, shoulders, tapering to the tail
    body = (
        _bezier([(256, 58), (300, 74), (302, 150), (292, 230)])
        + _bezier([(292, 230), (286, 290), (276, 322), (268, 340)])
        + [(244, 340)]
        + _bezier([(236, 322), (226, 290), (220, 230), (220, 230)])
        + _bezier([(210, 150), (212, 74), (256, 58), (256, 58)])
    )

    # long tail, fanned, with only a shallow central notch
    tail = (
        [(240, 330), (272, 330)]
        + _bezier([(272, 330), (288, 396), (300, 448), (306, 486)])
        + [(256, 452)]
        + _bezier([(206, 486), (212, 448), (224, 396), (240, 330)])
    )

    return [tail, wing, wing_left, body]


def to_svg_path(polys: list[list[tuple[float, float]]]) -> str:
    parts = []
    for poly in polys:
        d = f"M{poly[0][0]:.1f} {poly[0][1]:.1f}"
        for x, y in poly[1:]:
            d += f"L{x:.1f} {y:.1f}"
        parts.append(d + "Z")
    return " ".join(parts)


def rasterize(polys: list[list[tuple[float, float]]], size: int, rgba: tuple[int, int, int]) -> np.ndarray:
    """Supersampled fill so edges are smooth at small icon sizes."""
    ss = 4
    big = size * ss
    mask = np.zeros((big, big), dtype=np.uint8)

    import cv2

    for poly in polys:
        pts = np.array(
            [[int(round(x * big / SIZE)), int(round(y * big / SIZE))] for x, y in poly],
            dtype=np.int32,
        )
        cv2.fillPoly(mask, [pts], 255)

    alpha = cv2.resize(mask, (size, size), interpolation=cv2.INTER_AREA)
    out = np.zeros((size, size, 4), dtype=np.uint8)
    out[..., 0] = rgba[0]
    out[..., 1] = rgba[1]
    out[..., 2] = rgba[2]
    out[..., 3] = alpha
    return out


def write_png(path: pathlib.Path, rgba: np.ndarray) -> None:
    """Minimal PNG writer -- avoids a Pillow dependency just for icons."""
    h, w = rgba.shape[:2]
    raw = b"".join(b"\x00" + rgba[y].tobytes() for y in range(h))

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)


def write_ico(path: pathlib.Path, images: list[np.ndarray]) -> None:
    """ICO wrapping PNG-compressed entries (supported since Vista)."""
    blobs = []
    for img in images:
        tmp = path.parent / f".{path.stem}-{img.shape[0]}.tmp.png"
        write_png(tmp, img)
        blobs.append(tmp.read_bytes())
        tmp.unlink()

    header = struct.pack("<HHH", 0, 1, len(blobs))
    offset = 6 + 16 * len(blobs)
    entries, body = b"", b""
    for img, blob in zip(images, blobs):
        size = img.shape[0]
        entries += struct.pack(
            "<BBBBHHII", size if size < 256 else 0, size if size < 256 else 0,
            0, 0, 1, 32, len(blob), offset,
        )
        offset += len(blob)
        body += blob
    path.write_bytes(header + entries + body)


def main() -> None:
    polys = kestrel_polygons()
    path_d = to_svg_path(polys)

    dark = (229, 231, 235)   # light mark for dark UI
    light = (17, 24, 39)     # dark mark for light UI

    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        f'<path fill="currentColor" d="{path_d}"/>'
        "</svg>"
    )

    targets = {
        "web/images/branding/favicon.svg": svg,
        "docs/static/img/branding/logo.svg": svg.replace(
            'fill="currentColor"', f'fill="rgb{light}"'
        ),
        "docs/static/img/branding/logo-dark.svg": svg.replace(
            'fill="currentColor"', f'fill="rgb{dark}"'
        ),
    }
    for rel, content in targets.items():
        p = REPO_ROOT / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8", newline="\n")
        print(f"  wrote {rel}")

    rasters = {
        "web/images/branding/favicon-16x16.png": 16,
        "web/images/branding/favicon-32x32.png": 32,
        "web/images/branding/favicon.png": 512,
        "web/images/branding/apple-touch-icon.png": 180,
        "web/public/images/apple-touch-icon.png": 180,
        "web/public/images/android-chrome-192x192.png": 192,
        "web/public/images/android-chrome-512x512.png": 512,
        "web/public/images/maskable-icon.png": 180,
        "web/images/branding/mstile-150x150.png": 150,
        "docs/static/img/branding/kestrel.png": 512,
    }
    for rel, size in rasters.items():
        write_png(REPO_ROOT / rel, rasterize(polys, size, light))
        print(f"  wrote {rel} ({size}px)")

    for rel in ("web/images/branding/favicon.ico", "docs/static/img/branding/favicon.ico"):
        write_ico(
            REPO_ROOT / rel,
            [rasterize(polys, s, light) for s in (16, 32, 48)],
        )
        print(f"  wrote {rel}")

    # the inline mark used by the app header
    logo_tsx = REPO_ROOT / "web/src/components/Logo.tsx"
    logo_tsx.write_text(
        'import { cn } from "@/lib/utils";\n'
        "\n"
        "type LogoProps = {\n"
        "  className?: string;\n"
        "};\n"
        "\n"
        "// Generated by scripts/generate_brand_assets.py -- edit the mark there,\n"
        "// not here, so the SVG and the raster icons cannot drift apart.\n"
        "export default function Logo({ className }: LogoProps) {\n"
        "  return (\n"
        '    <svg viewBox="0 0 512 512" className={cn("fill-current", className)}>\n'
        f'      <path d="{path_d}" />\n'
        "    </svg>\n"
        "  );\n"
        "}\n",
        encoding="utf-8",
        newline="\n",
    )
    print("  wrote web/src/components/Logo.tsx")


if __name__ == "__main__":
    main()
