"""Render jianpu (numbered musical notation) as a vertical PNG image using Pillow."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont


# --- Layout constants ---
HEADER_HEIGHT = 80
NOTE_AREA_TOP = 80

# Vertical zones within each note row (relative to row top)
HIGH_OCTAVE_ZONE = 15      # space for high octave dots above digit
DIGIT_ZONE = 30             # space for note digit + accidental
LOW_OCTAVE_ZONE = 15        # space for low octave dots below digit
DURATION_ZONE = 25          # space for duration marks (lines, dots)
ROW_HEIGHT = HIGH_OCTAVE_ZONE + DIGIT_ZONE + LOW_OCTAVE_ZONE + DURATION_ZONE  # 85

ROW_GAP = 30                # gap between rows
NOTE_WIDTH = 45             # horizontal space per note token
NOTE_PADDING = 10           # extra padding after each note
BAR_GAP = 20                # extra space around bar lines
BARS_PER_LINE = 4           # bars per visual line
LEFT_MARGIN = 40
RIGHT_MARGIN = 40
TOP_MARGIN = 20

# Colors
BG_COLOR = (255, 255, 255)
NOTE_COLOR = (30, 30, 30)
ACCENTAL_COLOR = (80, 80, 80)
DURATION_COLOR = (60, 60, 60)
BAR_COLOR = (100, 100, 100)
HEADER_COLOR = (80, 80, 80)
TITLE_COLOR = (30, 30, 30)


@dataclass
class ParsedNote:
    """A single parsed jianpu token."""
    digit: str              # "0"-"9", or "?" for unplayable
    accidental: str         # "" or "#"
    high_octaves: int       # count of '
    low_octaves: int        # count of ,
    duration_marks: str     # raw suffix like "-", "/.", "//", etc.


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Find a suitable font with CJK support."""
    import sys
    candidates = []
    if sys.platform == "win32":
        import os
        fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")
        if bold:
            candidates = [
                os.path.join(fonts_dir, "msyhbd.ttc"),
                os.path.join(fonts_dir, "simhei.ttf"),
                os.path.join(fonts_dir, "msyh.ttc"),
            ]
        else:
            candidates = [
                os.path.join(fonts_dir, "msyh.ttc"),
                os.path.join(fonts_dir, "simhei.ttf"),
                os.path.join(fonts_dir, "simsun.ttc"),
            ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _parse_q_line(line: str) -> list[list[ParsedNote]]:
    """Parse a Q: line into a list of bars, each bar being a list of ParsedNote."""
    # Remove "Q:" prefix
    content = line
    if content.startswith("Q"):
        colon_idx = content.find(":")
        if colon_idx != -1:
            content = content[colon_idx + 1:]

    # Split by bar lines
    bars: list[list[ParsedNote]] = []
    current_bar: list[ParsedNote] = []

    tokens = content.split()
    for token in tokens:
        if token == "|":
            if current_bar:
                bars.append(current_bar)
                current_bar = []
            continue

        # Skip empty tokens
        if not token:
            continue

        note = _parse_token(token)
        current_bar.append(note)

    if current_bar:
        bars.append(current_bar)

    return bars


def _parse_token(token: str) -> ParsedNote:
    """Parse a single jianpu token like '4#', '5,-', '3/.', '0---'."""
    i = 0
    n = len(token)

    # Digit (0-9) or ?
    digit = ""
    if i < n and (token[i].isdigit() or token[i] == "?"):
        digit = token[i]
        i += 1

    # Accidentals: # or $
    accidental = ""
    while i < n and token[i] in ("#", "$"):
        accidental += "#"  # normalize $ to #
        i += 1

    # Octave markers
    high = 0
    low = 0
    while i < n and token[i] == "'":
        high += 1
        i += 1
    while i < n and token[i] == ",":
        low += 1
        i += 1

    # Duration marks: -, /, .
    duration = ""
    while i < n and token[i] in ("-", "/", "."):
        duration += token[i]
        i += 1

    return ParsedNote(
        digit=digit,
        accidental=accidental,
        high_octaves=high,
        low_octaves=low,
        duration_marks=duration,
    )


def _get_font_sizes() -> dict:
    """Get font sizes for different elements."""
    return {
        "title": _find_font(22, bold=True),
        "meta": _find_font(14),
        "digit": _find_font(28, bold=True),
        "accidental": _find_font(16),
        "octave_dot": _find_font(12),
        "duration_dash": _find_font(20),
        "rest_zero": _find_font(28, bold=True),
    }


def _measure_bar_width(notes: list[ParsedNote]) -> int:
    """Measure the pixel width of a bar."""
    width = 0
    for note in notes:
        # Digit width
        w = NOTE_WIDTH
        # Duration augmentation dashes extend the width
        dash_count = note.duration_marks.count("-")
        if dash_count > 0:
            w += dash_count * 12
        # Dots and slashes are drawn below, don't extend width much
        width += w + NOTE_PADDING
    return max(width, NOTE_WIDTH)


def _draw_header(
    draw: ImageDraw.ImageDraw,
    title: str,
    key: str,
    time_sig: str,
    tempo: int,
    fonts: dict,
    canvas_width: int,
) -> None:
    """Draw the title and metadata header."""
    # Title
    title_text = f"{title} - 简谱"
    draw.text((LEFT_MARGIN, TOP_MARGIN), title_text, fill=TITLE_COLOR, font=fonts["title"])

    # Metadata line
    meta_y = TOP_MARGIN + 30
    meta_parts = [
        f"调号: {key}",
        f"拍号: {time_sig}",
        f"速度: {tempo} BPM",
    ]
    meta_text = "    ".join(meta_parts)
    draw.text((LEFT_MARGIN, meta_y), meta_text, fill=HEADER_COLOR, font=fonts["meta"])

    # Separator line
    sep_y = TOP_MARGIN + 55
    draw.line([(LEFT_MARGIN, sep_y), (canvas_width - RIGHT_MARGIN, sep_y)], fill=(200, 200, 200), width=1)


def _draw_note(
    draw: ImageDraw.ImageDraw,
    note: ParsedNote,
    x: int,
    row_top: int,
    fonts: dict,
) -> int:
    """Draw a single note at position (x, row_top). Returns the width consumed."""
    center_x = x + NOTE_WIDTH // 2

    # 1. High octave dots
    if note.high_octaves > 0:
        dot_y = row_top + 2
        for j in range(note.high_octaves):
            dot_x = center_x - 3 + j * 10
            draw.ellipse(
                [dot_x, dot_y, dot_x + 6, dot_y + 6],
                fill=NOTE_COLOR,
            )

    # 2. Note digit (center of digit zone)
    digit_y = row_top + HIGH_OCTAVE_ZONE
    if note.digit == "0":
        # Rest: draw 0 with a slash through it or just plain 0
        bbox = fonts["rest_zero"].getbbox("0")
        tw = bbox[2] - bbox[0]
        draw.text(
            (center_x - tw // 2, digit_y),
            "0",
            fill=NOTE_COLOR,
            font=fonts["rest_zero"],
        )
    elif note.digit == "?":
        bbox = fonts["digit"].getbbox("?")
        tw = bbox[2] - bbox[0]
        draw.text(
            (center_x - tw // 2, digit_y),
            "?",
            fill=(200, 50, 50),
            font=fonts["digit"],
        )
    else:
        # Draw digit
        bbox = fonts["digit"].getbbox(note.digit)
        tw = bbox[2] - bbox[0]
        draw.text(
            (center_x - tw // 2, digit_y),
            note.digit,
            fill=NOTE_COLOR,
            font=fonts["digit"],
        )

        # Draw accidental (#) after digit
        if note.accidental:
            acc_x = center_x + tw // 2 + 2
            draw.text(
                (acc_x, digit_y + 4),
                "#",
                fill=ACCENTAL_COLOR,
                font=fonts["accidental"],
            )

    # 3. Low octave dots
    if note.low_octaves > 0:
        dot_y = row_top + HIGH_OCTAVE_ZONE + DIGIT_ZONE + 2
        for j in range(note.low_octaves):
            dot_x = center_x - 3 + j * 10
            draw.ellipse(
                [dot_x, dot_y, dot_x + 6, dot_y + 6],
                fill=NOTE_COLOR,
            )

    # 4. Duration marks
    dur_y = row_top + HIGH_OCTAVE_ZONE + DIGIT_ZONE + LOW_OCTAVE_ZONE + 2
    dur_x = x

    dm = note.duration_marks
    if dm:
        # Parse duration marks: combination of -, /, .
        # Augmentation dashes: draw horizontal lines below the digit
        dash_count = dm.count("-")
        dot_count = dm.count(".")
        slash_count = dm.count("/")

        line_start_x = x + 4
        line_end_x = x + NOTE_WIDTH + dash_count * 12 - 4
        line_y = dur_y + 10

        if dash_count > 0:
            # Draw augmentation line(s)
            for d in range(dash_count):
                ly = line_y + d * 5
                draw.line(
                    [(line_start_x, ly), (line_end_x, ly)],
                    fill=DURATION_COLOR,
                    width=2,
                )

        if slash_count > 0:
            # Draw diminution slashes (diagonal lines)
            for s in range(slash_count):
                sx = center_x - 8 + s * 8
                draw.line(
                    [(sx, dur_y + 16), (sx + 8, dur_y + 2)],
                    fill=DURATION_COLOR,
                    width=2,
                )

        if dot_count > 0:
            # Draw dot(s) to the right
            dot_x = line_end_x + 4
            draw.ellipse(
                [dot_x, line_y - 3, dot_x + 6, line_y + 3],
                fill=DURATION_COLOR,
            )

    # Return width consumed
    extra = dm.count("-") * 12
    return NOTE_WIDTH + NOTE_PADDING + extra


def _draw_bar_line(
    draw: ImageDraw.ImageDraw,
    x: int,
    row_top: int,
) -> None:
    """Draw a bar line (vertical line)."""
    y1 = row_top + 2
    y2 = row_top + ROW_HEIGHT - 2
    draw.line([(x, y1), (x, y2)], fill=BAR_COLOR, width=2)


def render_jianpu_image(
    jianpu_lines: list[str],
    title: str,
    key: str,
    time_sig: str,
    tempo: int,
    output_path: Path,
) -> Path:
    """Render jianpu lines as a vertical notation PNG image.

    Args:
        jianpu_lines: Q: lines from generate_jianpu_score
        title: Song title (audio stem)
        key: Transposed key for display
        time_sig: Time signature string (e.g. "4/4")
        tempo: BPM
        output_path: Where to write the PNG

    Returns:
        Path to the written PNG file.
    """
    fonts = _get_font_sizes()

    # Parse all Q: lines into bars
    all_bars: list[list[list[ParsedNote]]] = []
    for line in jianpu_lines:
        bars = _parse_q_line(line)
        all_bars.append(bars)

    # Flatten into a single sequence of bars
    flat_bars: list[list[ParsedNote]] = []
    for bars in all_bars:
        flat_bars.extend(bars)

    if not flat_bars:
        flat_bars = [[ParsedNote("0", "", 0, 0, "---")]]

    # Group bars into visual lines (BARS_PER_LINE bars per line)
    visual_lines: list[list[list[ParsedNote]]] = []
    for i in range(0, len(flat_bars), BARS_PER_LINE):
        visual_lines.append(flat_bars[i : i + BARS_PER_LINE])

    # Calculate canvas width: measure the widest visual line
    max_line_width = 0
    for vline in visual_lines:
        line_width = 0
        for bar in vline:
            line_width += _measure_bar_width(bar) + BAR_GAP
        line_width += BAR_GAP  # trailing bar line space
        max_line_width = max(max_line_width, line_width)

    canvas_width = max(600, LEFT_MARGIN + max_line_width + RIGHT_MARGIN)
    canvas_height = (
        TOP_MARGIN
        + HEADER_HEIGHT
        + len(visual_lines) * (ROW_HEIGHT + ROW_GAP)
        + 40  # bottom padding
    )

    # Create image
    img = Image.new("RGB", (canvas_width, canvas_height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    # Draw header
    _draw_header(draw, title, key, time_sig, tempo, fonts, canvas_width)

    # Draw each visual line
    for line_idx, vline in enumerate(visual_lines):
        row_top = NOTE_AREA_TOP + line_idx * (ROW_HEIGHT + ROW_GAP)
        x = LEFT_MARGIN

        # Opening bar line
        _draw_bar_line(draw, x, row_top)
        x += BAR_GAP

        for bar_idx, bar in enumerate(vline):
            # Draw notes in this bar
            for note in bar:
                w = _draw_note(draw, note, x, row_top, fonts)
                x += w

            # Closing bar line
            x += BAR_GAP // 2
            _draw_bar_line(draw, x, row_top)
            x += BAR_GAP

    # Save
    img.save(str(output_path), "PNG")
    return output_path
