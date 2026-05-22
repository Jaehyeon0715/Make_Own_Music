# -*- coding: utf-8 -*-
"""Generate launcher/icon.ico for the PyInstaller build."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def make_icon(out_path: Path) -> None:
    sizes = [16, 24, 32, 48, 64, 128, 256]
    base = 256
    img = Image.new("RGBA", (base, base), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((10, 10, base - 10, base - 10), fill=(40, 124, 116), outline=(255, 255, 255, 230), width=10)
    try:
        font = ImageFont.truetype("arial.ttf", 150)
    except OSError:
        font = ImageFont.load_default()
    text = "M"
    bbox = d.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((base - tw) / 2 - bbox[0], (base - th) / 2 - bbox[1] - 8), text, fill="white", font=font)
    img.save(out_path, format="ICO", sizes=[(s, s) for s in sizes])


if __name__ == "__main__":
    out = Path(__file__).resolve().parent / "icon.ico"
    make_icon(out)
    print(f"Wrote {out}")
