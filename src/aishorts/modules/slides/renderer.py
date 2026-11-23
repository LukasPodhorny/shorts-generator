"""Deterministic, CPU-only slide rendering. Text is measured, never cropped."""

from functools import lru_cache
from importlib.resources import files
from pathlib import Path
import math

from PIL import Image, ImageColor, ImageDraw, ImageFont

from aishorts.modules.script.script import SlideMedia
from aishorts.modules.slides.style import PALETTES, SlideRenderConfig, layout_regions


class SlideOverflowError(ValueError):
    """A slide cannot fit legibly; ask the script writer to shorten it."""


@lru_cache(maxsize=128)
def _font(size: int, bold: bool = False):
    filename = "InterDisplay-Bold.ttf" if bold else "Inter-Regular.ttf"
    return ImageFont.truetype(str(files("aishorts.resources") / "fonts" / filename), size)


def _wrap(draw, text, font, width):
    lines = []
    for paragraph in text.splitlines() or [""]:
        line = ""
        for word in paragraph.split():
            if draw.textlength(word, font=font) > width:
                # URLs and long unbroken words still fit without disappearing.
                pieces, piece = [], ""
                for char in word:
                    if piece and draw.textlength(piece + char, font=font) > width:
                        pieces.append(piece)
                        piece = ""
                    piece += char
                pieces.append(piece)
            else:
                pieces = [word]
            for piece in pieces:
                candidate = f"{line} {piece}".strip()
                if line and draw.textlength(candidate, font=font) > width:
                    lines.append(line)
                    line = piece
                else:
                    line = candidate
        lines.append(line)
    return lines


def _measure(draw, text, size, bold, width):
    font = _font(size, bold)
    lines = _wrap(draw, text, font, width) if text.strip() else []
    return font, lines, round(size * 1.26)


def _height(block):
    _, lines, leading = block
    return len(lines) * leading


def _paint(draw, block, x, y, color):
    font, lines, leading = block
    for i, line in enumerate(lines):
        draw.text((x, y + i * leading), line, font=font, fill=color, anchor="lt")


def _fit(draw, text, width, height, size, minimum, bold=False):
    for chosen in range(size, minimum - 1, -1):
        block = _measure(draw, text, chosen, bold, width)
        if _height(block) <= height:
            return block
    raise SlideOverflowError(f"Text does not fit at {minimum}px: {text[:80]!r}")


def text_box(draw, text, box, color, size=38, minimum=26, bold=False):
    """Fit with wrapping and bounded font reduction; fail instead of clipping."""
    if not text:
        return 0
    x, y, width, height = box
    block = _fit(draw, text, width, height, size, minimum, bold)
    _paint(draw, block, x, y, color)
    return _height(block)


def _items(draw, slide, box, palette, accent, *, portrait, has_visual):
    x, y, w, h = box
    count = len(slide.items)
    process = slide.layout == "process"
    comparison = slide.layout == "comparison"
    columns = 1
    if w >= 1250 and count > 1:
        columns = count if process and count <= 3 else 2
    horizontal_process = process and columns > 1
    gap = 26 if columns > 1 or not has_visual else 18
    cell_w = (w - gap * (columns - 1)) // columns
    pad_x = 32 if comparison or columns > 1 else 12
    gutter = pad_x
    if process and not horizontal_process:
        gutter += 62
    elif not comparison and not process:
        gutter += 32
    top = 72 if horizontal_process else 24
    bottom = 19 if has_visual else 26
    width = cell_w - gutter - pad_x
    heading_size, body_size = (54, 41) if not has_visual else (44, 34)
    if not portrait and columns == 1:
        heading_size, body_size = (40, 32) if has_visual else (50, 36)

    # Fit the group as a whole. Cards take the height of their text, and only
    # cards on the same row share a height.
    for reduction in range(max(heading_size - 25, body_size - 23) + 1):
        cells = []
        for item in slide.items:
            heading = _measure(draw, item.heading, max(25, heading_size - reduction), True, width)
            body = _measure(draw, item.body, max(23, body_size - reduction), False, width)
            body_gap = 9 if _height(body) else 0
            cells.append((heading, body, body_gap))
        row_heights = [
            top + max(_height(head) + spacing + _height(body) for head, body, spacing in cells[i:i + columns]) + bottom
            for i in range(0, count, columns)
        ]
        group_height = sum(row_heights) + gap * (len(row_heights) - 1)
        if group_height <= h:
            break
    else:
        raise SlideOverflowError("The teaching notes are too long for this layout")

    if has_visual:
        balance = 0.18 if portrait else 0.42
    else:
        balance = 0.14 if portrait else 0.26
    cy = y + int((h - group_height) * balance)
    for row, row_h in enumerate(row_heights):
        for col, (heading, body, body_gap) in enumerate(cells[row * columns:(row + 1) * columns]):
            i = row * columns + col
            cx = x + col * (cell_w + gap)
            if comparison or columns > 1:
                draw.rounded_rectangle((cx, cy, cx + cell_w, cy + row_h), radius=22, fill=palette["panel"])

            if process:
                sx, sy = cx + pad_x, cy + 16
                if columns == 1 and i + 1 < count:
                    draw.line((sx + 22, sy + 42, sx + 22, cy + row_h + gap + 16),
                              fill=palette["line"], width=2)
                draw.rounded_rectangle((sx, sy, sx + 44, sy + 38), radius=9, outline=accent, width=2)
                draw.text((sx + 22, sy + 19), f"{i + 1:02d}", fill=palette["ink"],
                          font=_font(21, True), anchor="mm")
                if horizontal_process and col + 1 < columns and i + 1 < count:
                    draw.line((cx + cell_w + 2, sy + 19, cx + cell_w + gap - 2, sy + 19), fill=accent, width=2)
            elif not comparison:
                dot_y = cy + top + 14
                draw.rounded_rectangle((cx + pad_x, dot_y, cx + pad_x + 15, dot_y + 5), radius=2, fill=accent)
            tx, ty = cx + gutter, cy + top
            _paint(draw, heading, tx, ty, palette["ink"])
            _paint(draw, body, tx, ty + _height(heading) + body_gap, palette["muted"])
        cy += row_h + gap


def _chart(draw, slide, box, palette, accent):
    x, y, w, h = box
    # Zero-based, signed horizontal bars: negative values are never made positive.
    values = [point.value for point in slide.chart]
    lo, hi = min(0, min(values)), max(0, max(values))
    if hi == lo:
        hi = 1
    label_w = w * 0.28
    plot_x, plot_w = x + label_w, w * 0.49
    zero_x = plot_x + (0 - lo) / (hi - lo) * plot_w
    row_h = min(94, (h - 42) / len(values))
    plot_h = row_h * len(values)
    y += int((h - plot_h - 42) * 0.38)
    draw.line((zero_x, y, zero_x, y + plot_h), fill=palette["line"], width=2)
    for i, point in enumerate(slide.chart):
        row_y = y + i * row_h
        label = _fit(draw, point.label, label_w - 20, row_h - 4, 30, 21)
        _paint(draw, label, x, row_y + (row_h - _height(label)) / 2, palette["ink"])
        end_x = plot_x + (point.value - lo) / (hi - lo) * plot_w
        left, right = sorted((zero_x, end_x))
        mid_y = row_y + row_h / 2
        half_bar = min(15, row_h / 4)
        draw.rounded_rectangle((plot_x, mid_y - half_bar, plot_x + plot_w, mid_y + half_bar),
                               radius=5, fill=palette["panel"], outline=palette["line"])
        if right - left >= 1:
            draw.rounded_rectangle((left, mid_y - half_bar, right, mid_y + half_bar), radius=5, fill=accent)
        value = f"{point.value:,.6g} {slide.unit}".strip()
        amount = _fit(draw, value, w * 0.23 - 18, row_h - 4, 28, 20, True)
        _paint(draw, amount, plot_x + plot_w + 18, row_y + (row_h - _height(amount)) / 2, palette["ink"])
    draw.text((zero_x, y + plot_h + 8), "0", font=_font(20), fill=palette["muted"], anchor="mt")


def _line_chart(draw, slide, box, palette, accent):
    x, y, w, h = box
    left, right = x + 94, x + w - 94
    top, bottom = y + 44, y + h - 104
    if right - left < 240 or bottom - top < 170:
        raise SlideOverflowError("Line chart needs more room; remove the supporting visual")
    points = slide.chart
    xmin, xmax = points[0].x, points[-1].x
    values = [point.value for point in points]
    ymin, ymax = min(values), max(values)
    padding = max((ymax - ymin) * 0.12, abs(ymax) * 0.05, 1e-6)
    ymin, ymax = ymin - padding, ymax + padding

    def px(value):
        return left + (value - xmin) / (xmax - xmin) * (right - left)

    def py(value):
        return bottom - (value - ymin) / (ymax - ymin) * (bottom - top)

    target = (ymax - ymin) / 4
    magnitude = 10 ** math.floor(math.log10(target))
    step = max(candidate * magnitude for candidate in (1, 2, 2.5, 5, 10)
               if candidate * magnitude <= target)
    first = math.ceil(ymin / step)
    last = math.floor(ymax / step)
    for index in range(first, last + 1):
        value = index * step
        level = py(value)
        draw.line((left, level, right, level), fill=palette["line"], width=3 if index == 0 else 2)
        draw.text((left - 16, level), f"{value:,.6g}", fill=palette["muted"], font=_font(25), anchor="rm")
    draw.line((left, bottom, right, bottom), fill=palette["muted"], width=2)
    coords = [(px(point.x), py(point.value)) for point in points]
    draw.line(coords, fill=accent, width=5, joint="curve")
    for cx, cy in coords:
        draw.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=accent,
                     outline=palette["bg"], width=3)
    # Avoid overlapping dates/categories. The validator can ask the writer to
    # select fewer points instead of silently hiding labels.
    label_width = min(138, max(74, (right - left) // len(points) - 10))
    prior_right = float("-inf")
    for point, (cx, _) in zip(points, coords):
        label = _fit(draw, point.label, label_width, 70, 27, 21)
        widest = max((draw.textlength(line, font=label[0]) for line in label[1]), default=0)
        label_left = cx - widest / 2
        if label_left < prior_right + 8 or label_left < x or label_left + widest > x + w:
            raise SlideOverflowError("Line chart labels overlap; use fewer or shorter labels")
        for line_index, line in enumerate(label[1]):
            draw.text((cx, bottom + 16 + line_index * label[2]), line,
                      fill=palette["muted"], font=label[0], anchor="mt")
        prior_right = label_left + widest
    if slide.unit:
        draw.text((left, y), slide.unit, fill=palette["muted"], font=_font(22), anchor="lt")
    if slide.x_unit:
        draw.text((right, y + h - 15), slide.x_unit, fill=palette["muted"], font=_font(22), anchor="rb")


def _proportion(draw, slide, box, palette, accent):
    x, y, w, h = box
    count = len(slide.chart)
    total = sum(point.value for point in slide.chart)
    base = ImageColor.getrgb(palette["bg"])
    highlight = ImageColor.getrgb(accent)
    colors = [tuple(round(base[j] * (1 - mix) + highlight[j] * mix) for j in range(3))
              for mix in (1.0, 0.78, 0.60, 0.43, 0.29)]
    bar_h = min(112, max(70, int(h * 0.20)))
    columns = 1 if w < 850 else 3 if count == 3 and w >= 1200 else 2
    rows = (count + columns - 1) // columns
    gap = 52 if columns > 1 else 0
    row_h = min(110, (h - bar_h - 30) // rows)
    if row_h < 58:
        raise SlideOverflowError("Proportion labels need more room")
    group_h = bar_h + 30 + row_h * rows
    bar_y = y + int((h - group_h) * 0.48)
    left = x
    for index, point in enumerate(slide.chart):
        right = x + w if index == count - 1 else left + w * point.value / total
        draw.rectangle((left, bar_y, right, bar_y + bar_h), fill=colors[index])
        left = right
    legend_y = bar_y + bar_h + 30
    col_w = (w - gap * (columns - 1)) // columns
    for index, point in enumerate(slide.chart):
        col, row = index % columns, index // columns
        lx = x + col * (col_w + gap)
        ly = legend_y + row * row_h
        draw.ellipse((lx, ly + 16, lx + 23, ly + 39), fill=colors[index])
        percent = f"{point.value / total * 100:.1f}".rstrip("0").rstrip(".") + "%"
        value_width = draw.textlength(percent, font=_font(36, True))
        label = _fit(draw, point.label, col_w - value_width - 68, row_h - 4, 40, 25)
        _paint(draw, label, lx + 38, ly, palette["ink"])
        draw.text((lx + col_w - 8, ly + 2), percent, fill=palette["ink"],
                  font=_font(36, True), anchor="rt")


def _cycle(draw, slide, box, palette, accent):
    x, y, w, h = box
    count = len(slide.items)
    node_w = min(470, int(w * 0.43))
    node_h = min(220, int(h * 0.36))
    if node_w < 180 or node_h < 118:
        raise SlideOverflowError("Cycle diagram needs more room")
    if count == 3:
        centers = [(x + w / 2, y + node_h / 2 + 12),
                   (x + w - node_w / 2 - 8, y + h - node_h / 2 - 12),
                   (x + node_w / 2 + 8, y + h - node_h / 2 - 12)]
    else:
        centers = [(x + node_w / 2 + 8, y + node_h / 2 + 8),
                   (x + w - node_w / 2 - 8, y + node_h / 2 + 8),
                   (x + w - node_w / 2 - 8, y + h - node_h / 2 - 8),
                   (x + node_w / 2 + 8, y + h - node_h / 2 - 8)]
    for first, second in zip(centers, centers[1:] + centers[:1]):
        ax, ay = first
        bx, by = second
        dx, dy = bx - ax, by - ay
        length = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / length, dy / length
        inset = max(node_w if abs(ux) > abs(uy) else node_h, 1) * 0.52
        start = (ax + ux * inset, ay + uy * inset)
        end = (bx - ux * inset, by - uy * inset)
        draw.line((start, end), fill=accent, width=3)
        draw.polygon((end, (end[0] - ux * 13 - uy * 7, end[1] - uy * 13 + ux * 7),
                      (end[0] - ux * 13 + uy * 7, end[1] - uy * 13 - ux * 7)), fill=accent)
    for item, (cx, cy) in zip(slide.items, centers):
        left, top = cx - node_w / 2, cy - node_h / 2
        draw.rounded_rectangle((left, top, left + node_w, top + node_h), radius=18,
                               fill=palette["panel"])
        title = _fit(draw, item.heading, node_w - 42, 86, 42, 26, True)
        body = _fit(draw, item.body, node_w - 42, node_h - _height(title) - 38, 30, 21)
        total_height = _height(title) + (8 if body[1] else 0) + _height(body)
        text_y = top + (node_h - total_height) / 2
        _paint(draw, title, left + 21, text_y, palette["ink"])
        _paint(draw, body, left + 21, text_y + _height(title) + 8, palette["muted"])


@lru_cache(maxsize=6)
def _background(width, height, theme, mode):
    palette = PALETTES[theme]
    if mode != "lecture":
        return Image.new("RGB", (width, height), palette["bg"])
    gradient = Image.linear_gradient("L").rotate(90).resize((width, height))
    colors = tuple(ImageColor.getrgb(palette[key]) for key in ("bg", "wash"))
    channels = [
        gradient.point([round(start + (end - start) * v / 255) for v in range(256)])
        for start, end in zip(*colors)
    ]
    return Image.merge("RGB", channels)


def _metrics(draw, slide, box, palette, accent):
    x, y, w, h = box
    columns = len(slide.items) if w >= 1120 else 1
    gap = 54
    width = (w - gap * (columns - 1)) // columns
    rows = (len(slide.items) + columns - 1) // columns
    band = min(264, h // rows)
    y += int((h - band * rows) * (0.32 if columns == 1 else 0.48))
    size = max(30, min(136, int(min(band * 0.65, band - 62) / 1.26)))
    longest_value = max(draw.textlength(item.heading, font=_font(size, True)) for item in slide.items)
    size = max(30, min(size, int(size * width / max(longest_value, 1))))
    value_height = round(size * 1.26)
    for i, item in enumerate(slide.items):
        left = x + i % columns * (width + gap)
        top = y + i // columns * band
        text_box(draw, item.heading, (left, top, width, value_height),
                 accent, size=size, minimum=30, bold=True)
        text_box(draw, item.body, (left, top + value_height + 10, width, band - value_height - 24),
                 palette["ink"], size=42 if w >= 900 else 34, minimum=22)


def _donut(draw, slide, box, palette, accent):
    x, y, w, h = box
    stacked = h >= 820
    chart_w = w if stacked else int(w * 0.49)
    diameter = min(int(chart_w * (0.67 if stacked else 0.91)), int(h * (0.50 if stacked else 0.91)), 540)
    cx = x + (chart_w - diameter) // 2
    cy = y if stacked else y + (h - diameter) // 2
    legend_x = x if stacked else x + chart_w + 24
    legend_y = cy + diameter + 40 if stacked else y
    legend_w = x + w - legend_x
    legend_h = y + h - legend_y
    row = min(92, legend_h // len(slide.chart))
    legend_y += (legend_h - row * len(slide.chart)) // 2
    label_size = 40 if legend_w >= 540 else 30
    value_font = _font(label_size, True)
    value_width = draw.textlength("100.0%", font=value_font) + 22
    total = sum(point.value for point in slide.chart)
    colors = (accent, "#BC735A", "#6A8799", "#C5A45D", "#88769D")
    theta = -90.0
    for i, point in enumerate(slide.chart):
        share = point.value / total
        end = theta + 360 * share
        draw.pieslice((cx, cy, cx + diameter, cy + diameter), theta, end, fill=colors[i])
        theta = end
        middle = legend_y + (i + 0.5) * row
        draw.ellipse((legend_x, middle - 9, legend_x + 18, middle + 9), fill=colors[i])
        label = _fit(draw, point.label, legend_w - 34 - value_width, row - 4, label_size, 20)
        _paint(draw, label, legend_x + 34, middle - _height(label) / 2, palette["ink"])
        percent = f"{share * 100:.1f}".rstrip("0").rstrip(".")
        draw.text((legend_x + legend_w, middle), "<0.1%" if percent == "0" else f"{percent}%",
                  fill=palette["ink"], font=value_font, anchor="rm")
    inset = int(diameter * 0.27)
    draw.ellipse((cx + inset, cy + inset, cx + diameter - inset, cy + diameter - inset), fill=palette["bg"])


def _timeline(draw, slide, box, palette, accent):
    x, y, w, h = box
    count = len(slide.items)
    horizontal = w >= 1200
    gap = 26
    gutter = 66
    item_w = (w - gap * (count - 1)) // count if horizontal else w - gutter
    stride = min(224, h // count)
    top = y + max(0, (h - 190) // 2) if horizontal else y + int((h - stride * count) * 0.20)
    dot = 12
    step = item_w + gap
    if horizontal:
        draw.line((x + dot, top + dot, x + step * (count - 1) + dot, top + dot), fill=palette["line"], width=3)
    else:
        draw.line((x + dot, top + dot, x + dot, top + stride * (count - 1) + dot), fill=palette["line"], width=3)
    heading_size, body_size = (54, 42) if not horizontal and w >= 900 else (40, 31)
    for i, item in enumerate(slide.items):
        left = x + i * step if horizontal else x
        cy = top if horizontal else top + i * stride
        draw.ellipse((left, cy, left + 2 * dot, cy + 2 * dot), fill=accent)
        tx, ty = (left, cy + 44) if horizontal else (left + gutter, cy)
        budget = y + h - ty if horizontal else stride - 12
        used = text_box(draw, item.heading, (tx, ty, item_w, int(budget * (0.5 if item.body else 1))),
                        palette["ink"], size=heading_size, minimum=25, bold=True)
        text_box(draw, item.body, (tx, ty + used + 6, item_w, budget - used - 6),
                 palette["muted"], size=body_size, minimum=21)


def _hero(draw, slide, box, palette):
    x, y, width, height = box
    head_size = 105 if width >= 900 else 84
    subtitle = _fit(draw, slide.subtitle, min(width, 1100), height * 0.40, 47, 28)
    gap = 28 if _height(subtitle) else 0
    headline = _fit(draw, slide.title, min(width, 1370), height - _height(subtitle) - gap, head_size, 42, True)
    height_used = _height(headline) + gap + _height(subtitle)
    top = y + int((height - height_used) * 0.46)
    _paint(draw, headline, x, top, palette["ink"])
    _paint(draw, subtitle, x, top + _height(headline) + gap, palette["muted"])


def _scene_indicator(draw, config, margin, palette, accent):
    w = config.width
    if config.chapters > 1:
        right = w - margin
        count = f"{config.chapter:02d} / {config.chapters:02d}"
        font = _font(24, True)
        draw.text((right, 67), count, fill=palette["ink"], font=font, anchor="rm")
        if config.chapters <= 12:
            end = right - draw.textlength(count, font=font) - 24
            step = min(22, 148 // config.chapters)
            for i in range(config.chapters):
                left = end - (config.chapters - i) * step
                color = accent if i + 1 == config.chapter else palette["line"]
                draw.rounded_rectangle((left, 64, left + step - 5, 70), radius=3, fill=color)


def _credits(draw, slide, config, margin, y, palette):
    source = "  ·  ".join(filter(None, (slide.source.strip(), config.attribution.strip())))
    if not source:
        return
    width = config.width - 2 * margin
    font = _font(20)
    # Long media credits remain in the description. Avoid overflow after the
    # assets have already been retrieved.
    lines = _wrap(draw, source, font, width)
    if len(lines) > 2:
        lines = lines[:2]
        while draw.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    _paint(draw, (font, lines, 25), margin, y, palette["muted"])


def render_slide(slide: SlideMedia, config: SlideRenderConfig, output: str | Path | None = None):
    if (config.width, config.height) != ((1080, 1920) if config.mode == "briefing" else (1920, 1080)):
        raise ValueError("Slide dimensions must match the presentation mode")
    palette = PALETTES[config.style.theme]
    accent = config.style.accent_color
    image = _background(config.width, config.height, config.style.theme, config.mode).copy()
    draw = ImageDraw.Draw(image)
    portrait = config.mode == "briefing"
    w = image.width
    margin = 72 if portrait else 88
    _scene_indicator(draw, config, margin, palette, accent)
    box, visual = layout_regions(config, slide.layout)
    x, y, bw, bh = box
    if visual:
        vx, vy, vw, vh = visual
        draw.rectangle((vx, vy, vx + vw - 1, vy + vh - 1), fill=palette["panel"])
    if slide.layout in {"title", "spotlight"}:
        if visual is None:
            box = (x, 170, bw, 1360 if portrait else 670)
        _hero(draw, slide, box, palette)
    else:
        title_y = 156 if visual else 360 if portrait else 206
        title_h = (176 if portrait else 142) if visual else (258 if portrait else 184)
        used = text_box(draw, slide.title, (margin, title_y, w - 2 * margin, title_h),
                        palette["ink"], size=74 if portrait else 68, minimum=42, bold=True)
        if visual is None:
            bottom = y + bh
            y = title_y + used + (48 if portrait else 38)
            bh = bottom - y
        if slide.layout == "quote":
            quote = _fit(draw, slide.subtitle, min(bw - 42, 1250), bh, 62 if bw >= 850 else 50, 30)
            top = y + int((bh - _height(quote)) * 0.40)
            draw.rounded_rectangle((x, top, x + 5, top + _height(quote)), radius=2, fill=accent)
            _paint(draw, quote, x + 42, top, palette["ink"])
        elif slide.subtitle:
            used = text_box(draw, slide.subtitle, (x, y, bw, min(110, bh * 0.24)), palette["muted"], size=34, minimum=24)
            y, bh = y + used + 22, bh - used - 22
        if slide.layout == "chart":
            _chart(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "line_chart":
            _line_chart(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "proportion":
            _proportion(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "cycle":
            _cycle(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "metrics":
            _metrics(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "donut":
            _donut(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout == "timeline":
            _timeline(draw, slide, (x, y, bw, bh), palette, accent)
        elif slide.layout != "quote":
            _items(draw, slide, (x, y, bw, bh), palette, accent, portrait=portrait, has_visual=bool(visual))
    _credits(draw, slide, config, margin, 1660 if portrait else 889, palette)
    if output is None:
        return image
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)
    return str(path)
