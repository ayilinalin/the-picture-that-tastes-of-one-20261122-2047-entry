#!/usr/bin/env python3
"""Steaming ramen bowl — one delicious picture, drawn procedurally.

Python 3.13, standard library only, no network. Deterministic: two runs
produce byte-identical PNG output. Writes /output/entry.png (1024x1024).
"""
import hashlib
import math
import os
import struct
import zlib

W = 1024
H = 1024
OUT = "/output/entry.png"

# ---------------------------------------------------------------- canvas
# Pixel buffer, row-major RGB bytes.
buf = bytearray(W * H * 3)


def _idx(x, y):
    return (y * W + x) * 3


def put(x, y, r, g, b):
    if 0 <= x < W and 0 <= y < H:
        i = _idx(x, y)
        buf[i] = r
        buf[i + 1] = g
        buf[i + 2] = b


def blend(x, y, r, g, b, a):
    """Blend colour over existing pixel, a in 0..1."""
    if 0 <= x < W and 0 <= y < H and a > 0.0:
        i = _idx(x, y)
        if a >= 1.0:
            buf[i] = r
            buf[i + 1] = g
            buf[i + 2] = b
        else:
            ia = 1.0 - a
            buf[i] = int(buf[i] * ia + r * a)
            buf[i + 1] = int(buf[i + 1] * ia + g * a)
            buf[i + 2] = int(buf[i + 2] * ia + b * a)


def lerp(a, b, t):
    return a + (b - a) * t


def clamp255(v):
    return 0 if v < 0 else (255 if v > 255 else int(v))


def mix(c1, c2, t):
    return (clamp255(lerp(c1[0], c2[0], t)),
            clamp255(lerp(c1[1], c2[1], t)),
            clamp255(lerp(c1[2], c2[2], t)))


def hash01(x, y, seed=0):
    """Deterministic cheap pseudo-random in [0,1)."""
    h = (x * 374761393 + y * 668265263 + seed * 974634211) & 0xFFFFFFFF
    h ^= h >> 13
    h = (h * 1274126177) & 0xFFFFFFFF
    h ^= h >> 16
    return (h & 0xFFFFFF) / 16777216.0


def fill_rect(x0, y0, x1, y1, col):
    x0 = max(0, x0)
    y0 = max(0, y0)
    x1 = min(W, x1)
    y1 = min(H, y1)
    row = bytes(col) * (x1 - x0)
    for y in range(y0, y1):
        i = y * W * 3 + x0 * 3
        buf[i:i + len(row)] = row


def ellipse_span(cx, cy, rx, ry):
    """Yield (y, x0, x1) integer spans of a filled ellipse."""
    for y in range(max(0, int(cy - ry)), min(H, int(cy + ry) + 1)):
        dy = (y - cy) / ry
        d = 1.0 - dy * dy
        if d < 0:
            continue
        dx = rx * math.sqrt(d)
        yield y, int(cx - dx), int(cx + dx)


def fill_ellipse(cx, cy, rx, ry, col, alpha=1.0):
    for y, x0, x1 in ellipse_span(cx, cy, rx, ry):
        if alpha >= 1.0:
            row = bytes(col) * (x1 - x0 + 1)
            i = y * W * 3 + max(0, x0) * 3
            lo = max(0, x0)
            buf[i:i + len(row) - max(0, -x0) * 3] = row[: (min(W, x1 + 1) - lo) * 3]
        else:
            for x in range(max(0, x0), min(W, x1 + 1)):
                blend(x, y, col[0], col[1], col[2], alpha)


def disc(cx, cy, r, col, alpha=1.0):
    fill_ellipse(cx, cy, r, r, col, alpha)


def ring(cx, cy, rx, ry, thick, col, alpha=1.0):
    """Draw an ellipse ring by stamping the outline as small discs."""
    steps = int(2 * math.pi * max(rx, ry))
    for s in range(steps):
        t = 2 * math.pi * s / steps
        x = cx + rx * math.cos(t)
        y = cy + ry * math.sin(t)
        disc(int(x), int(y), thick, col, alpha)


def thick_line(x0, y0, x1, y1, w, col, alpha=1.0):
    dx = x1 - x0
    dy = y1 - y0
    dist = math.hypot(dx, dy)
    steps = max(1, int(dist))
    r = max(1, w // 2)
    for s in range(steps + 1):
        t = s / steps
        disc(int(x0 + dx * t), int(y0 + dy * t), r, col, alpha)


def polyline(points, w, col, alpha=1.0):
    for a, b in zip(points, points[1:]):
        thick_line(a[0], a[1], b[0], b[1], w, col, alpha)


def wavy_strand(x0, y0, x1, y1, amp, waves, w, col, shadow=True):
    """A noodle strand: sine wave between two points."""
    pts = []
    steps = 26
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy) or 1.0
    nx = -dy / length
    ny = dx / length
    for s in range(steps + 1):
        t = s / steps
        off = amp * math.sin(t * math.pi * waves * 2)
        pts.append((int(x0 + dx * t + nx * off),
                    int(y0 + dy * t + ny * off)))
    if shadow:
        sh = [(x + 3, y + 4) for x, y in pts]
        polyline(sh, w, (120, 70, 10), 0.35)
    polyline(pts, w, col, 1.0)
    # glossy top edge on the strand
    hi = [(x, y - max(1, w // 3)) for x, y in pts]
    polyline(hi, max(1, w // 3), (255, 225, 140), 0.55)


# ---------------------------------------------------------------- background
# Warm dark wooden table: vertical gradient + plank seams + soft grain.
TOP = (74, 44, 28)
BOT = (38, 22, 14)
for y in range(H):
    t = y / (H - 1)
    c = mix(TOP, BOT, t)
    # warm light from the upper left
    glow = max(0.0, 1.0 - math.hypot(0 - 0, y - 0) / 1400.0)
    row = bytes((clamp255(c[0] + 26 * glow), clamp255(c[1] + 16 * glow),
                 clamp255(c[2] + 6 * glow))) * W
    i = y * W * 3
    buf[i:i + len(row)] = row

# plank seams
for py in (255, 511, 767):
    for x in range(W):
        blend(x, py, 20, 10, 6, 0.35)
        blend(x, py + 1, 90, 55, 30, 0.18)
# sparse grain speckles (deterministic, low density keeps PNG small)
for y in range(0, H, 3):
    for x in range(0, W, 5):
        if hash01(x, y, 7) < 0.06:
            v = hash01(x, y, 11)
            if v < 0.5:
                blend(x, y, 96, 58, 32, 0.25)
            else:
                blend(x, y, 24, 12, 7, 0.30)

# soft warm pool of light behind the bowl
for y, x0, x1 in ellipse_span(430, 420, 520, 430):
    for x in range(max(0, x0), min(W, x1 + 1)):
        d = math.hypot((x - 430) / 520.0, (y - 420) / 430.0)
        if d < 1.0:
            blend(x, y, 255, 190, 110, 0.10 * (1.0 - d))

# ---------------------------------------------------------------- bowl shadow
fill_ellipse(512, 872, 400, 62, (12, 6, 4), 0.45)
fill_ellipse(512, 862, 350, 48, (12, 6, 4), 0.30)

# ---------------------------------------------------------------- bowl body
# Outer bowl: dark slate-blue ceramic, squat ellipse.
BCX, BCY = 512, 600
for y, x0, x1 in ellipse_span(BCX, BCY, 392, 300):
    for x in range(max(0, x0), min(W, x1 + 1)):
        # vertical shading: lighter near rim, darker at base
        t = (y - (BCY - 300)) / 600.0
        base = mix((58, 72, 96), (26, 32, 48), t)
        # warm light from upper left
        dl = math.hypot((x - 330) / 420.0, (y - 380) / 340.0)
        light = max(0.0, 1.0 - dl) * 0.55
        r = clamp255(base[0] + 70 * light)
        g = clamp255(base[1] + 60 * light)
        b = clamp255(base[2] + 40 * light)
        # subtle speckle
        if hash01(x, y, 3) < 0.04:
            r = clamp255(r + 8)
            g = clamp255(g + 8)
            b = clamp255(b + 8)
        put(x, y, r, g, b)

# bowl foot ring
ring(BCX, BCY + 218, 150, 42, 7, (18, 22, 34), 0.8)
# glossy highlight sweeping down the left of the bowl
for s in range(60):
    t = s / 59.0
    ang = math.pi * (0.62 + 0.55 * t)
    x = int(BCX + 330 * math.cos(ang))
    y = int(BCY + 250 * math.sin(ang))
    disc(x, y, 10, (150, 170, 205), 0.10)

# rim: thick pale slate ring
ring(BCX, BCY - 40, 372, 268, 26, (148, 162, 188), 1.0)
ring(BCX, BCY - 40, 372, 268, 12, (196, 208, 226), 0.9)
# rim shadow on the lower right
for s in range(40):
    t = s / 39.0
    ang = math.pi * (0.05 + 0.35 * t)
    x = int(BCX + 360 * math.cos(ang))
    y = int(BCY - 40 + 258 * math.sin(ang))
    disc(x, y, 9, (70, 82, 104), 0.35)

# ---------------------------------------------------------------- broth
# Golden broth surface inside the rim.
for y, x0, x1 in ellipse_span(BCX, BCY - 40, 344, 240):
    for x in range(max(0, x0), min(W, x1 + 1)):
        d = math.hypot((x - BCX) / 344.0, (y - (BCY - 40)) / 240.0)
        t = min(1.0, d)
        c = mix((255, 196, 90), (196, 110, 26), t * 0.85)
        # centre glow
        dc = math.hypot((x - 470) / 200.0, (y - 520) / 140.0)
        glow = max(0.0, 1.0 - dc) * 0.5
        r = clamp255(c[0] + 40 * glow)
        g = clamp255(c[1] + 26 * glow)
        b = clamp255(c[2] + 8 * glow)
        put(x, y, r, g, b)

# broth inner shadow just inside the rim
ring(BCX, BCY - 40, 336, 232, 10, (150, 80, 16), 0.35)

# chili-oil swirls: dark red arcs floating on the broth
for cx, cy, r, a0, a1 in ((430, 500, 120, 0.3, 2.4),
                          (620, 620, 95, 2.6, 4.6),
                          (520, 470, 70, 4.0, 5.6),
                          (380, 640, 80, 1.2, 3.0)):
    steps = 40
    for s in range(steps):
        t = s / (steps - 1)
        ang = a0 + (a1 - a0) * t
        x = int(cx + r * math.cos(ang))
        y = int(cy + r * 0.62 * math.sin(ang))
        disc(x, y, 7, (178, 44, 16), 0.55)
        disc(x, y - 2, 3, (214, 74, 28), 0.6)

# oil droplets: glossy golden beads
for cx, cy, r in ((470, 560, 12), (590, 500, 9), (400, 580, 8),
                  (650, 590, 11), (540, 660, 7), (350, 520, 6)):
    disc(cx, cy, r, (255, 214, 120), 0.85)
    disc(cx - 3, cy - 3, max(2, r // 3), (255, 244, 200), 0.9)

# two big gloss highlights on the broth
fill_ellipse(400, 470, 90, 34, (255, 236, 190), 0.35)
fill_ellipse(640, 640, 70, 26, (255, 226, 170), 0.28)

# ---------------------------------------------------------------- noodles
# Central raised mound of wavy golden strands.
NOODLE = (246, 196, 74)
NOODLE_D = (214, 150, 40)
strands = [
    (300, 560, 720, 540, 16, 3), (320, 600, 700, 580, 20, 4),
    (340, 640, 680, 620, 14, 3), (300, 520, 740, 500, 18, 4),
    (360, 680, 660, 660, 16, 3), (330, 480, 700, 470, 14, 5),
    (380, 700, 640, 690, 12, 3), (310, 580, 730, 610, 18, 4),
    (350, 540, 690, 520, 15, 5), (400, 720, 620, 700, 12, 3),
    (290, 620, 710, 640, 17, 4), (420, 470, 640, 460, 13, 5),
]
for x0, y0, x1, y1, amp, waves in strands:
    wavy_strand(x0, y0, x1, y1, amp, waves, 9, NOODLE)
# a few darker strands for depth
for x0, y0, x1, y1, amp, waves in ((330, 590, 700, 570, 18, 4),
                                   (360, 650, 670, 630, 15, 3),
                                   (320, 510, 710, 495, 16, 4)):
    wavy_strand(x0, y0, x1, y1, amp, waves, 7, NOODLE_D)

# noodle mound highlight: lifted curls in the middle (kept subtle so they
# read as noodle curls, not rings)
for cx, cy, r in ((512, 560, 40), (470, 600, 30), (560, 600, 28)):
    ring(cx, cy, r, int(r * 0.55), 5, NOODLE, 0.7)
    ring(cx, cy, r - 10, int((r - 10) * 0.55), 4, (255, 226, 140), 0.5)

# ---------------------------------------------------------------- toppings
# --- ajitama eggs (two halves, left and right of the mound) ---
def egg(cx, cy):
    # white: cream gradient ellipse, slightly tilted
    for y, x0, x1 in ellipse_span(cx, cy, 74, 58):
        for x in range(max(0, x0), min(W, x1 + 1)):
            d = math.hypot((x - cx) / 74.0, (y - cy) / 58.0)
            c = mix((255, 250, 238), (226, 204, 172), min(1.0, d))
            put(x, y, c[0], c[1], c[2])
    ring(cx, cy, 74, 58, 4, (190, 164, 128), 0.5)
    # yolk: glossy orange dome
    for y, x0, x1 in ellipse_span(cx, cy + 2, 40, 34):
        for x in range(max(0, x0), min(W, x1 + 1)):
            d = math.hypot((x - cx) / 40.0, (y - (cy + 2)) / 34.0)
            c = mix((255, 176, 66), (224, 110, 20), min(1.0, d * 0.9))
            put(x, y, c[0], c[1], c[2])
    disc(cx - 12, cy - 10, 11, (255, 224, 150), 0.85)
    disc(cx - 13, cy - 11, 5, (255, 244, 205), 0.9)


egg(392, 528)
egg(640, 548)

# --- chashu slices (two, leaning on the mound) ---
def chashu(cx, cy, tilt):
    # rolled pork: warm brown-red disc with a pale fat ring
    for y, x0, x1 in ellipse_span(cx, cy, 66, 56):
        for x in range(max(0, x0), min(W, x1 + 1)):
            d = math.hypot((x - cx) / 66.0, (y - cy) / 56.0)
            c = mix((176, 96, 52), (120, 58, 30), min(1.0, d))
            # marbling streaks
            if hash01(x, y, 21) < 0.10:
                c = mix(c, (232, 190, 150), 0.5)
            put(x, y, c[0], c[1], c[2])
    ring(cx, cy, 66, 56, 5, (96, 44, 22), 0.6)
    ring(cx, cy, 44, 36, 6, (238, 198, 158), 0.75)
    disc(cx - 18, cy - 16, 8, (214, 140, 96), 0.6)


chashu(560, 660, 0)
chashu(452, 686, 0)

# --- green onion rings scattered over the broth ---
ONION = (86, 178, 74)
ONION_D = (38, 120, 44)
for ox, oy, orad in ((330, 470, 13), (700, 500, 12), (740, 600, 13),
                     (300, 640, 11), (690, 680, 12), (360, 720, 11),
                     (620, 440, 10), (430, 440, 11), (760, 540, 10),
                     (290, 540, 10), (580, 730, 10), (480, 430, 9)):
    ring(ox, oy, orad, orad, 5, ONION, 1.0)
    ring(ox, oy, orad, orad, 2, (150, 220, 120), 0.8)
    disc(ox, oy, max(2, orad - 7), ONION_D, 0.9)

# --- nori sheet leaning on the rim, upper right ---
# dark green rectangle, slightly rotated, with a lighter edge
import math as _m
_nori = []
for i in range(150):
    for j in range(96):
        # rotate a 150x96 sheet by -18 degrees around its centre
        px = i - 75
        py = j - 48
        ca, sa = _m.cos(-0.31), _m.sin(-0.31)
        rx = int(760 + px * ca - py * sa)
        ry = int(420 + px * sa + py * ca)
        shade = 22 + int(10 * hash01(i, j, 31))
        col = (16 + shade // 3, 34 + shade // 2, 18 + shade // 4)
        if i < 4 or j < 4:
            col = (52, 84, 48)
        blend(rx, ry, col[0], col[1], col[2], 0.96)

# ---------------------------------------------------------------- chopsticks
# Two wooden sticks resting across the right rim.
def stick(x0, y0, x1, y1, w):
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    steps = int(dist)
    for s in range(steps + 1):
        t = s / steps
        ww = w * (1.0 - 0.45 * t)  # taper to the tip
        cx = int(x0 + dx * t)
        cy = int(y0 + dy * t)
        disc(cx, cy, max(2, int(ww / 2)), (146, 96, 52), 1.0)
        disc(cx - 1, cy - 1, max(1, int(ww / 4)), (196, 140, 84), 0.9)


stick(700, 330, 900, 640, 15)
stick(724, 322, 930, 620, 15)

# ---------------------------------------------------------------- steam
# Thin white wavy wisps rising above the bowl, soft and fading upward.
for base_x, phase, amp, alpha in ((430, 0.0, 26, 0.13),
                                  (512, 1.3, 32, 0.10),
                                  (590, 2.6, 24, 0.11),
                                  (470, 4.0, 20, 0.08)):
    pts = []
    for s in range(30):
        t = s / 29.0
        y = int(330 - t * 190)
        x = int(base_x + amp * math.sin(t * 5.0 + phase) * (0.4 + t))
        pts.append((x, y))
    # fade the wisp as it rises: draw in three segments, alpha falling
    for seg in range(3):
        lo = seg * 10
        hi = min(29, lo + 10)
        a = alpha * (1.0 - seg * 0.3)
        polyline(pts[lo:hi + 1], 16, (255, 255, 255), a)
        polyline(pts[lo:hi + 1], 7, (255, 255, 255), a * 0.8)

# ---------------------------------------------------------------- vignette
for y in range(H):
    for x in range(0, W, 2):
        d = math.hypot((x - 512) / 640.0, (y - 512) / 640.0)
        if d > 0.75:
            a = min(0.38, (d - 0.75) * 1.1)
            blend(x, y, 10, 5, 3, a)
            blend(x + 1, y, 10, 5, 3, a)

# ---------------------------------------------------------------- PNG encode
def chunk(typ, data):
    c = struct.pack(">I", len(data)) + typ + data
    c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
    return c


def main():
    os.makedirs("/output", exist_ok=True)
    raw = bytearray()
    for y in range(H):
        raw.append(0)  # filter: none
        i = y * W * 3
        raw += buf[i:i + W * 3]
    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + chunk(b"IEND", b""))
    with open(OUT, "wb") as f:
        f.write(png)
    print("wrote", OUT, len(png), "bytes",
          hashlib.sha256(png).hexdigest())


if __name__ == "__main__":
    main()
