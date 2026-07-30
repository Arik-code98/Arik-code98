from __future__ import annotations

from collections import deque
from html import escape
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parents[1]
SOURCE_IMAGE = ROOT / "assets" / "source" / "portrait.jpeg"
OUTPUT_SVG = ROOT / "assets" / "generated" / "portrait.svg"

ASCII_RAMP = " .`:-=+*cs#%@"
COLS = 90
FONT_SIZE = 12.8
CHAR_WIDTH = 7.42
LINE_HEIGHT = 15.2
PADDING_X = 28
PADDING_Y = 24


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
    rgb = image.convert("RGB")
    width, height = rgb.size
    scale = min(1.0, 420 / max(width, height))
    if scale != 1.0:
        probe = rgb.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    else:
        probe = rgb

    probe_width, probe_height = probe.size
    background = sample_background_color(probe)
    visited = [[False] * probe_width for _ in range(probe_height)]
    queue: deque[tuple[int, int]] = deque()

    def maybe_enqueue(x: int, y: int) -> None:
        if 0 <= x < probe_width and 0 <= y < probe_height and not visited[y][x]:
            pixel = probe.getpixel((x, y))
            if color_distance(pixel, background) < 64:
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

    subject_pixels: list[tuple[int, int]] = []
    for y in range(probe_height):
        for x in range(probe_width):
            if not visited[y][x]:
                subject_pixels.append((x, y))

    if not subject_pixels:
        return (0, 0, width, height)

    left = min(x for x, _ in subject_pixels)
    right = max(x for x, _ in subject_pixels)
    top = min(y for _, y in subject_pixels)
    bottom = max(y for _, y in subject_pixels)

    expand_x = int((right - left + 1) * 0.16)
    expand_top = int((bottom - top + 1) * 0.14)
    expand_bottom = int((bottom - top + 1) * 0.10)

    left = max(0, left - expand_x)
    right = min(probe_width - 1, right + expand_x)
    top = max(0, top - expand_top)
    bottom = min(probe_height - 1, bottom + expand_bottom)

    inv = 1 / scale
    return (
        int(left * inv),
        int(top * inv),
        int((right + 1) * inv),
        int((bottom + 1) * inv),
    )


def preprocess_image(image_path: Path) -> Image.Image:
    image = Image.open(image_path).convert("RGB")
    crop_box = find_subject_bbox(image)
    cropped = image.crop(crop_box)

    background = Image.new("RGB", cropped.size, (255, 255, 255))
    rgb = cropped.convert("RGB")
    bg_color = sample_background_color(image)
    pixels = []
    for y in range(rgb.height):
        for x in range(rgb.width):
            pixel = rgb.getpixel((x, y))
            if color_distance(pixel, bg_color) < 58 and y < int(rgb.height * 0.92):
                pixels.append((255, 255, 255))
            else:
                pixels.append(pixel)
    background.putdata(pixels)

    grayscale = ImageOps.grayscale(background)
    grayscale = ImageOps.autocontrast(grayscale, cutoff=1)
    grayscale = grayscale.filter(ImageFilter.SMOOTH_MORE)

    def tone_curve(value: int) -> int:
        normalized = value / 255
        curved = normalized ** 1.52
        return int(curved * 255)

    return grayscale.point(tone_curve)


def image_to_ascii_rows(image: Image.Image, cols: int = COLS) -> list[str]:
    width, height = image.size
    rows = max(32, int(cols * (height / width) * 0.54))
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


def build_svg(rows: list[str]) -> str:
    max_cols = max(len(row) for row in rows)
    body_width = max_cols * CHAR_WIDTH
    body_height = len(rows) * LINE_HEIGHT
    width = int(body_width + PADDING_X * 2)
    height = int(body_height + PADDING_Y * 2 + 16)

    defs: list[str] = []
    content: list[str] = []
    cursor_color = "#d49a66"
    ink = "#f7e7d6"
    muted = "#aa8b71"

    for index, row in enumerate(rows):
        row_width = max(6, len(row) * CHAR_WIDTH)
        y = PADDING_Y + (index + 1) * LINE_HEIGHT
        begin = index * 0.08
        duration = 0.24
        clip_id = f"line-{index}"
        defs.append(
            f"""
    <clipPath id="{clip_id}">
      <rect x="{PADDING_X}" y="{y - LINE_HEIGHT + 3:.2f}" width="0" height="{LINE_HEIGHT:.2f}" rx="2">
        <animate attributeName="width" from="0" to="{row_width:.2f}" begin="{begin:.2f}s" dur="{duration:.2f}s" fill="freeze" />
      </rect>
    </clipPath>"""
        )
        content.append(
            f"""
  <text xml:space="preserve" x="{PADDING_X}" y="{y:.2f}" clip-path="url(#{clip_id})">{escape(row)}</text>
  <rect x="{PADDING_X}" y="{y - LINE_HEIGHT + 4:.2f}" width="8" height="{LINE_HEIGHT - 3:.2f}" rx="1.5" fill="{cursor_color}" opacity="0.88">
    <animate attributeName="x" from="{PADDING_X}" to="{PADDING_X + row_width:.2f}" begin="{begin:.2f}s" dur="{duration:.2f}s" fill="freeze" />
    <set attributeName="opacity" to="0" begin="{begin + duration:.2f}s" />
  </rect>"""
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">
  <title id="title">Animated ASCII portrait of Arik Chakraborty</title>
  <desc id="desc">A self-typing monochrome portrait rendered from ASCII characters.</desc>
  <defs>{''.join(defs)}
  </defs>
  <rect width="{width}" height="{height}" rx="22" fill="#130f0c" />
  <rect x="1" y="1" width="{width - 2}" height="{height - 2}" rx="21" fill="none" stroke="#2d221c" />
  <text x="{PADDING_X}" y="16" fill="{muted}" font-size="10.5" font-family="'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace" letter-spacing="1.2">PROFILE.PORTRAIT / AUTO-GENERATED</text>
  <g fill="{ink}" font-size="{FONT_SIZE}" font-family="'SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace">{''.join(content)}
  </g>
</svg>
"""


def main() -> None:
    if not SOURCE_IMAGE.exists():
        raise FileNotFoundError(f"Missing portrait source: {SOURCE_IMAGE}")
    processed = preprocess_image(SOURCE_IMAGE)
    rows = image_to_ascii_rows(processed)
    OUTPUT_SVG.write_text(build_svg(rows), encoding="utf-8")
    print(f"Wrote {OUTPUT_SVG}")


if __name__ == "__main__":
    main()

