#!/usr/bin/env python3
"""Regenerate the PNG icons in this directory. Run by hand when the mark changes:

    python3 internal/webui/assets/icons/generate.py internal/webui/assets/icons

Rasterises the panel's Electro mark (a lightning bolt) to PNG.

The mark already exists as an SVG (internal/webui/handlers_app.go) and that is
what desktop browsers use. iOS ignores SVG for a home-screen icon, and Android's
maskable icons want a real bitmap with a safe zone, so the same artwork is drawn
here as a signed distance field and written out as PNG. No rasteriser is needed
on the machine and the geometry stays in one place: the numbers below are the
SVG's own polygon points.
"""
import math, struct, zlib

# --- the artwork, in the SVG's 128x128 coordinate space -----------------------
BOLT = [(72, 16), (30, 72), (58, 72), (50, 112), (98, 54), (70, 54)]
GROW = 3.0                   # half of the SVG's stroke-width:6 (rounds the corners)
INK = (0xE0, 0x21, 0x2F)     # the Electro red
GRAD = ((0x26, 0x14, 0x15), (0x07, 0x05, 0x05))   # the panel's dark, warm ground


def sd_segment(px, py, ax, ay, bx, by):
    vx, vy, wx, wy = bx - ax, by - ay, px - ax, py - ay
    d = vx * vx + vy * vy
    t = 0.0 if d == 0 else max(0.0, min(1.0, (wx * vx + wy * vy) / d))
    return math.hypot(wx - t * vx, wy - t * vy)


def sd_round_box(px, py, x0, y0, x1, y1, r):
    """Signed distance to a rounded rectangle; negative inside."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    hx, hy = (x1 - x0) / 2, (y1 - y0) / 2
    qx, qy = px - cx, py - cy
    rr = r[1] if qx > 0 else r[0]        # right pair vs left pair
    if qy > 0:
        rr = r[2] if qx > 0 else r[3]
    dx, dy = abs(qx) - hx + rr, abs(qy) - hy + rr
    outside = math.hypot(max(dx, 0.0), max(dy, 0.0))
    return outside + min(max(dx, dy), 0.0) - rr


def sd_polygon(px, py, pts):
    """Signed distance to a simple polygon; negative inside."""
    d = float("inf")
    inside = False
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx, by = pts[(i + 1) % n]
        d = min(d, sd_segment(px, py, ax, ay, bx, by))
        if (ay > py) != (by > py) and px < (bx - ax) * (py - ay) / (by - ay) + ax:
            inside = not inside
    return -d if inside else d


def glyph_distance(x, y):
    """Distance to the filled, corner-rounded bolt: <=0 is ink."""
    return sd_polygon(x, y, BOLT) - GROW


def cover(d, px_per_unit):
    """SDF -> coverage, antialiased over one device pixel."""
    return max(0.0, min(1.0, 0.5 - d * px_per_unit))


def render(size, inset=0.0, rounded=True):
    """One icon. `inset` shrinks the artwork to leave a maskable safe zone."""
    scale = size / 128.0
    art = 1.0 - 2.0 * inset
    rows = []
    for py in range(size):
        row = bytearray([0])                        # PNG filter: none
        for px in range(size):
            # device pixel -> art space
            u = (px + 0.5) / size
            v = (py + 0.5) / size
            x = ((u - inset) / art) * 128.0
            y = ((v - inset) / art) * 128.0

            if rounded:
                bg = cover(sd_round_box(x, y, 0, 0, 128, 128, (30,) * 4), scale * art)
            else:
                bg = 1.0                            # maskable: the OS clips it
            if bg <= 0.0:
                row += b"\x00\x00\x00\x00"
                continue

            t = min(1.0, max(0.0, (x + y) / 256.0))  # the SVG's diagonal gradient
            r = GRAD[0][0] + (GRAD[1][0] - GRAD[0][0]) * t
            g = GRAD[0][1] + (GRAD[1][1] - GRAD[0][1]) * t
            b = GRAD[0][2] + (GRAD[1][2] - GRAD[0][2]) * t

            ink = cover(glyph_distance(x, y), scale * art)
            r += (INK[0] - r) * ink
            g += (INK[1] - g) * ink
            b += (INK[2] - b) * ink
            row += bytes((int(r + 0.5), int(g + 0.5), int(b + 0.5), int(bg * 255 + 0.5)))
        rows.append(bytes(row))
    return png(size, size, b"".join(rows))


def png(w, h, raw):
    def chunk(tag, data):
        c = tag + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9))
            + chunk(b"IEND", b""))


if __name__ == "__main__":
    import sys
    out = sys.argv[1].rstrip("/")
    for name, size, inset, rounded in [
        ("icon-192.png", 192, 0.0, True),
        ("icon-512.png", 512, 0.0, True),
        # Maskable: Android may crop to a circle, so the mark is pulled inside
        # the 80% safe zone and the background runs edge to edge.
        ("icon-maskable-512.png", 512, 0.14, False),
        # iOS composites its own rounding and shows no transparency.
        ("apple-touch-icon.png", 180, 0.0, False),
    ]:
        data = render(size, inset, rounded)
        open(f"{out}/{name}", "wb").write(data)
        print(f"{name:26} {size}x{size}  {len(data):6} bytes")
