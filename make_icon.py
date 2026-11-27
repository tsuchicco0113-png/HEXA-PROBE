#!/usr/bin/env python3
"""HEXA PROBE のランチャー用アイコン: 光る紫の六角形に虫めがね
usage: python3 make_icon.py OUT.png [SIZE | REFERENCE.png]"""
import math
import sys

from PIL import Image, ImageDraw, ImageFilter


def hexpts(cx, cy, r):
    return [(cx + r * math.cos(math.radians(60 * i + 30)), cy + r * math.sin(math.radians(60 * i + 30)))
            for i in range(6)]


def make(size):
    s = size * 4
    u = s / 100
    acc = (176, 132, 255, 255)
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    glow = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    pts = hexpts(50 * u, 50 * u, 44 * u)
    ImageDraw.Draw(glow).line(pts + [pts[0]], fill=(176, 132, 255, 200), width=int(10 * u))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(4 * u)))
    d = ImageDraw.Draw(img)
    d.polygon(pts, fill=(20, 16, 32, 255))
    d.line(pts + [pts[0]], fill=acc, width=int(4 * u), joint="curve")
    # 虫めがね: レンズの中に小さな六角形
    cx, cy, r = 44 * u, 44 * u, 17 * u
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(235, 238, 245, 255), width=int(5 * u))
    inner = hexpts(cx, cy, 8 * u)
    d.polygon(inner, fill=(90, 220, 240, 255))
    d.line([(cx + r * 0.72, cy + r * 0.72), (72 * u, 72 * u)], fill=(235, 238, 245, 255), width=int(8 * u))
    return img.resize((size, size), Image.LANCZOS)


def main():
    out, size = sys.argv[1], 64
    if len(sys.argv) > 2:
        arg = sys.argv[2]
        if arg.lower().endswith(".png"):
            try:
                size = Image.open(arg).size[0]
            except OSError:
                pass
        else:
            size = int(arg)
    make(size).save(out)
    print(f"icon {size}x{size} -> {out}")


if __name__ == "__main__":
    main()
