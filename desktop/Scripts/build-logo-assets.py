from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


NAVY = "#081927"
NAVY_EDGE = "#16384B"
CYAN = "#24D2DC"
AZURE = "#4D88FF"
INK = "#17202A"
MUTED = "#667281"


def scaled_points(points: list[tuple[float, float]], scale: float) -> list[tuple[int, int]]:
    return [(round(x * scale), round(y * scale)) for x, y in points]


def draw_round_line(
    draw: ImageDraw.ImageDraw,
    points: list[tuple[float, float]],
    width: float,
    fill: str,
    scale: float,
) -> None:
    rendered = scaled_points(points, scale)
    rendered_width = max(1, round(width * scale))
    draw.line(rendered, fill=fill, width=rendered_width, joint="curve")
    radius = rendered_width // 2
    for x, y in (rendered[0], rendered[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)


def render_icon(size: int, supersample: int = 4) -> Image.Image:
    canvas_size = size * supersample
    scale = canvas_size / 256
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    inset = round(8 * scale)
    radius = round(58 * scale)
    draw.rounded_rectangle(
        (inset, inset, canvas_size - inset, canvas_size - inset),
        radius=radius,
        fill=NAVY,
        outline=NAVY_EDGE,
        width=max(1, round(2 * scale)),
    )

    # Two continuous ribbons form a forward-moving W without relying on small text.
    draw_round_line(draw, [(58, 76), (91, 178), (128, 112)], 25, CYAN, scale)
    draw_round_line(draw, [(128, 112), (165, 178), (198, 76)], 25, AZURE, scale)

    return image.resize((size, size), Image.Resampling.LANCZOS)


def svg_source() -> str:
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">
  <rect x="8" y="8" width="240" height="240" rx="58" fill="#081927" stroke="#16384B" stroke-width="2"/>
  <path d="M58 76 91 178 128 112" fill="none" stroke="#24D2DC" stroke-width="25" stroke-linecap="round" stroke-linejoin="round"/>
  <path d="M128 112 165 178 198 76" fill="none" stroke="#4D88FF" stroke-width="25" stroke-linecap="round" stroke-linejoin="round"/>
</svg>
"""


def font(size: int, semibold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    names = [
        "C:/Windows/Fonts/seguisb.ttf" if semibold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for name in names:
        path = Path(name)
        if path.exists():
            return ImageFont.truetype(str(path), size=size)
    return ImageFont.load_default()


def create_preview(icon: Image.Image, output: Path) -> None:
    width, height = 1280, 760
    preview = Image.new("RGB", (width, height), "#F4F6F8")
    draw = ImageDraw.Draw(preview)

    draw.rounded_rectangle((54, 48, 1226, 712), radius=32, fill="white", outline="#DDE3EA", width=2)
    draw.text((96, 90), "Wukong ROM Studio", fill=INK, font=font(38, semibold=True))
    draw.text((96, 145), "Modern app identity / icon system", fill=MUTED, font=font(20))

    large = icon.resize((320, 320), Image.Resampling.LANCZOS)
    preview.paste(large, (96, 220), large)

    draw.text((474, 230), "BUILD FORWARD", fill="#0B6BCB", font=font(18, semibold=True))
    draw.text((474, 270), "A geometric W built from two continuous ribbons.", fill=INK, font=font(26, semibold=True))
    draw.text((474, 315), "Cyan communicates tooling and live diagnostics.", fill=MUTED, font=font(19))
    draw.text((474, 348), "Azure communicates stability, output and progress.", fill=MUTED, font=font(19))

    draw.rounded_rectangle((474, 410, 1138, 492), radius=16, fill="#F3F3F3", outline="#D7DCE2")
    title_icon = icon.resize((52, 52), Image.Resampling.LANCZOS)
    preview.paste(title_icon, (494, 425), title_icon)
    draw.text((562, 432), "Wukong ROM Studio", fill=INK, font=font(23, semibold=True))
    draw.text((798, 437), "San sang", fill=MUTED, font=font(17))

    draw.text((474, 545), "Small-size clarity", fill=INK, font=font(20, semibold=True))
    x = 474
    for icon_size in (16, 20, 24, 32, 48, 64, 96):
        tile = 94
        draw.rounded_rectangle((x, 585, x + tile, 677), radius=14, fill="#EDF1F5")
        rendered = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
        px = x + (tile - icon_size) // 2
        py = 596 + (64 - icon_size) // 2
        preview.paste(rendered, (px, py), rendered)
        label = str(icon_size)
        label_box = draw.textbbox((0, 0), label, font=font(14))
        draw.text((x + (tile - (label_box[2] - label_box[0])) / 2, 653), label, fill=MUTED, font=font(14))
        x += tile + 10

    output.parent.mkdir(parents=True, exist_ok=True)
    preview.save(output, format="PNG", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Wukong Studio logo assets.")
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Desktop solution root.",
    )
    args = parser.parse_args()

    assets = args.root / "WukongStudio.App" / "Assets"
    artifacts = args.root / "artifacts"
    assets.mkdir(parents=True, exist_ok=True)
    artifacts.mkdir(parents=True, exist_ok=True)

    icon_512 = render_icon(512)
    icon_512.save(assets / "WukongStudio.png", format="PNG", optimize=True)
    (assets / "WukongStudio.svg").write_text(svg_source(), encoding="ascii")

    ico_sizes = [16, 20, 24, 32, 40, 48, 64, 128, 256]
    icon_256 = render_icon(256)
    icon_256.save(assets / "WukongStudio.ico", format="ICO", sizes=[(size, size) for size in ico_sizes])
    create_preview(icon_512, artifacts / "wukong-logo-preview.png")

    print(f"Logo assets written to {assets}")


if __name__ == "__main__":
    main()
