from __future__ import annotations

from collections import deque
from html import escape
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGE = ROOT / "assets" / "source" / "portrait.png"
OUTPUT_SVG = ROOT / "assets" / "generated" / "portrait.svg"

ASCII_RAMP = " .,:-=+*#%@"
DEFAULT_COLS = 96
MONO = "'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace"


def average(samples: Iterable[tuple[int, int, int]]) -> tuple[float, float, float]:
    values = list(samples)
    total = len(values) or 1
    return tuple(sum(pixel[index] for pixel in values) / total for index in range(3))


def sample_background_color(image: Image.Image) -> tuple[float, float, float]:
    rgb = image.convert("RGB")
    width, height = rgb.size
    patch = max(12, min(width, height) // 14)
    samples: list[tuple[int, int, int]] = []
    corners = [
        (0, 0, patch, patch),
        (width - patch, 0, width, patch),
        (0, height - patch, patch, height),
        (width - patch, height - patch, width, height),
    ]
    for left, top, right, bottom in corners:
        for x in range(left, right):
            for y in range(top, bottom):
                samples.append(rgb.getpixel((x, y)))
    return average(samples)


def color_distance(pixel: tuple[int, int, int], background: tuple[float, float, float]) -> float:
    return sum((channel - bg) ** 2 for channel, bg in zip(pixel, background)) ** 0.5


def find_subject_bbox(image: Image.Image) -> tuple[int, int, int, int]:
    if "A" in image.getbands():
        alpha = image.getchannel("A")
        if alpha.getextrema()[0] < 255:
            bbox = alpha.getbbox()
            if bbox:
                left, top, right, bottom = bbox
                padding_x = int((right - left) * 0.06)
                padding_top = int((bottom - top) * 0.04)
                return (
                    max(0, left - padding_x),
                    max(0, top - padding_top),
                    min(image.width, right + padding_x),
                    bottom,
                )

    rgb = image.convert("RGB")
    width, height = rgb.size
    scale = min(1.0, 420 / max(width, height))
    probe = rgb.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS) if scale != 1.0 else rgb

    probe_width, probe_height = probe.size
    background = sample_background_color(probe)
    visited = [[False] * probe_width for _ in range(probe_height)]
    queue: deque[tuple[int, int]] = deque()

    def maybe_enqueue(x: int, y: int) -> None:
        if 0 <= x < probe_width and 0 <= y < probe_height and not visited[y][x]:
            pixel = probe.getpixel((x, y))
            if color_distance(pixel, background) < 62:
                visited[y][x] = True
                queue.append((x, y))

    for x in range(probe_width):
        maybe_enqueue(x, 0)
        maybe_enqueue(x, probe_height - 1)
    for y in range(probe_height):
        maybe_enqueue(0, y)
        maybe_enqueue(probe_width - 1, y)

    while queue:
        x, y = queue.popleft()
        maybe_enqueue(x - 1, y)
        maybe_enqueue(x + 1, y)
        maybe_enqueue(x, y - 1)
        maybe_enqueue(x, y + 1)

    subject_pixels = [(x, y) for y in range(probe_height) for x in range(probe_width) if not visited[y][x]]
    if not subject_pixels:
        return (0, 0, width, height)

    left = min(x for x, _ in subject_pixels)
    right = max(x for x, _ in subject_pixels)
    top = min(y for _, y in subject_pixels)
    bottom = max(y for _, y in subject_pixels)

    subject_width = right - left + 1
    subject_height = bottom - top + 1
    left = max(0, left - int(subject_width * 0.12))
    right = min(probe_width - 1, right + int(subject_width * 0.12))
    top = max(0, top - int(subject_height * 0.16))

    # Keep the portrait focused for photos that include a background.
    face_bottom = top + int(subject_height * 0.70)
    bottom = min(bottom, face_bottom, probe_height - 1)

    inv = 1 / scale
    return (
        int(left * inv),
        int(top * inv),
        int((right + 1) * inv),
        int((bottom + 1) * inv),
    )


def preprocess_image(image_path: Path) -> Image.Image:
    source = Image.open(image_path)
    cropped = source.crop(find_subject_bbox(source))

    if "A" in source.getbands():
        canvas = Image.new("RGBA", cropped.size, (255, 255, 255, 255))
        image = Image.alpha_composite(canvas, cropped.convert("RGBA")).convert("RGB")
        grayscale = ImageOps.grayscale(image)
        grayscale = grayscale.filter(ImageFilter.GaussianBlur(radius=0.7))
        grayscale = ImageOps.autocontrast(grayscale, cutoff=1)

        def tone_curve(value: int) -> int:
            normalized = value / 255
            curved = normalized ** 1.7
            return int(curved * 255)

        return grayscale.point(tone_curve)

    image = source.convert("RGB")
    cropped = image.crop(find_subject_bbox(image))

    background = Image.new("RGB", cropped.size, (255, 255, 255))
    rgb = cropped.convert("RGB")
    bg_color = sample_background_color(image)
    pixels = []
    for y in range(rgb.height):
        for x in range(rgb.width):
            pixel = rgb.getpixel((x, y))
            if color_distance(pixel, bg_color) < 58 and y < int(rgb.height * 0.94):
                pixels.append((255, 255, 255))
            else:
                pixels.append(pixel)
    background.putdata(pixels)

    grayscale = ImageOps.grayscale(background)
    grayscale = grayscale.filter(ImageFilter.GaussianBlur(radius=0.7))
    grayscale = ImageOps.autocontrast(grayscale, cutoff=1)

    def tone_curve(value: int) -> int:
        normalized = value / 255
        curved = normalized ** 1.7
        return int(curved * 255)

    return grayscale.point(tone_curve)


def build_ascii_rows(image_path: Path = SOURCE_IMAGE, cols: int = DEFAULT_COLS) -> list[str]:
    image = preprocess_image(image_path)
    width, height = image.size
    rows = max(34, int(cols * (height / width) * 0.48))
    sampled = image.resize((cols, rows), Image.Resampling.LANCZOS)

    lines: list[str] = []
    for y in range(rows):
        chars = []
        for x in range(cols):
            value = sampled.getpixel((x, y))
            index = round((255 - value) / 255 * (len(ASCII_RAMP) - 1))
            chars.append(ASCII_RAMP[index])
        lines.append("".join(chars).rstrip())
    return lines


def render_ascii_layers(
    rows: list[str],
    *,
    x: float,
    y: float,
    font_size: float,
    char_width: float,
    line_height: float,
    color: str,
    cursor_color: str,
    animate: bool,
) -> tuple[str, str, float, float]:
    defs: list[str] = []
    body: list[str] = []
    max_cols = max(len(row) for row in rows) if rows else 0
    total_width = max_cols * char_width
    total_height = len(rows) * line_height

    for index, row in enumerate(rows):
        row_width = max(6.0, len(row) * char_width)
        row_y = y + (index + 1) * line_height
        if animate:
            begin = index * 0.09
            duration = 0.22
            clip_id = f"line-{index}"
            defs.append(
                f"""
    <clipPath id="{clip_id}">
      <rect x="{x:.2f}" y="{row_y - line_height + 2:.2f}" width="0" height="{line_height:.2f}">
        <animate attributeName="width" from="0" to="{row_width:.2f}" begin="{begin:.2f}s" dur="{duration:.2f}s" fill="freeze" />
      </rect>
    </clipPath>"""
            )
            body.append(
                f"""
  <text xml:space="preserve" x="{x:.2f}" y="{row_y:.2f}" clip-path="url(#{clip_id})">{escape(row)}</text>
  <rect x="{x:.2f}" y="{row_y - line_height + 3:.2f}" width="{max(5.0, char_width * 0.92):.2f}" height="{line_height - 2:.2f}" fill="{cursor_color}" opacity="0.92">
    <animate attributeName="x" from="{x:.2f}" to="{x + row_width:.2f}" begin="{begin:.2f}s" dur="{duration:.2f}s" fill="freeze" />
    <set attributeName="opacity" to="0" begin="{begin + duration:.2f}s" />
  </rect>"""
            )
        else:
            body.append(f'\n  <text xml:space="preserve" x="{x:.2f}" y="{row_y:.2f}">{escape(row)}</text>')

    group = (
        f'<g fill="{color}" font-size="{font_size}" '
        f'font-family="{MONO}" letter-spacing="0">{ "".join(body) }\n</g>'
    )
    return "".join(defs), group, total_width, total_height


def build_svg(rows: list[str]) -> str:
    font_size = 10.4
    char_width = 6.15
    line_height = 11.9
    defs, portrait, total_width, total_height = render_ascii_layers(
        rows,
        x=28,
        y=22,
        font_size=font_size,
        char_width=char_width,
        line_height=line_height,
        color="#e6edf3",
        cursor_color="#c9d1d9",
        animate=True,
    )
    width = int(total_width + 56)
    height = int(total_height + 46)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Animated ASCII portrait of Arik Chakraborty</title>
  <desc id="desc">A self-typing monochrome portrait rendered from ASCII characters.</desc>
  <defs>{defs}
  </defs>
  <rect width="{width}" height="{height}" rx="16" fill="#0d1117" />
  {portrait}
</svg>
"""


def main() -> None:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Missing portrait source: {SOURCE_IMAGE}")
    rows = build_ascii_rows()
    OUTPUT_SVG.write_text(build_svg(rows), encoding="utf-8")
    print(f"Wrote {OUTPUT_SVG}")


if __name__ == "__main__":
    main()
