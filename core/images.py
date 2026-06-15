from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from domain import Platform, PLATFORMS
from storage.assets import check_fonts, FONTS_DIR


FONT_MEDIUM   = "Inter-Medium.ttf"
FONT_SEMIBOLD = "Inter-SemiBold.ttf"

# Number of quote cards generated per platform per run
PLATFORM_COUNTS: dict[str, int] = {
    "ig_story":    5,
    "ig_portrait": 5,
    "twitter":     3,
    "linkedin":    3,
}


# ── Font loader ───────────────────────────────────────────────────────────────

def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS_DIR / name), size)


def get_font_for_background(bg_color: tuple) -> tuple:
    """Return (text_color, shadow_color) based on background luminance."""
    r, g, b = bg_color[:3]
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    if luminance > 0.5:
        return (30, 30, 30), (200, 200, 200)
    return (255, 255, 255), (30, 30, 30)


# ── Per-platform renderers ────────────────────────────────────────────────────

def render_story(caption: str, cover_art: Image.Image, index: int, output_path: Path) -> Path:
    """
    IG Story (1080x1920) — tall centered stack.
    Cover art fills top half, caption centered in bottom half.
    """
    W, H = 1080, 1920
    canvas = Image.new("RGB", (W, H), (15, 15, 15))

    art = cover_art.resize((W, W), Image.LANCZOS)
    canvas.paste(art, (0, 0))

    overlay = Image.new("RGBA", (W, H // 2), (15, 15, 15, 230))
    canvas.paste(overlay.convert("RGB"), (0, H // 2), mask=overlay.split()[3])

    draw = ImageDraw.Draw(canvas)
    font = _font(FONT_SEMIBOLD, 52)
    text_color, _ = get_font_for_background((15, 15, 15))
    _draw_wrapped_text(draw, caption, font, text_color, box=(80, H // 2 + 80, W - 80, H - 80))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path


def render_portrait(caption: str, cover_art: Image.Image, index: int, output_path: Path) -> Path:
    """
    IG Post Portrait (1080x1350) — cover art top third, caption below.
    """
    W, H = 1080, 1350
    canvas = Image.new("RGB", (W, H), (15, 15, 15))

    art_h = 450
    art = cover_art.resize((W, art_h), Image.LANCZOS)
    canvas.paste(art, (0, 0))

    draw = ImageDraw.Draw(canvas)
    font = _font(FONT_SEMIBOLD, 48)
    text_color, _ = get_font_for_background((15, 15, 15))
    _draw_wrapped_text(draw, caption, font, text_color, box=(80, art_h + 80, W - 80, H - 80))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path


def render_twitter(caption: str, cover_art: Image.Image, index: int, output_path: Path) -> Path:
    """
    Twitter/X (1600x900) — landscape. Cover art left column, text right column.
    """
    W, H = 1600, 900
    canvas = Image.new("RGB", (W, H), (15, 15, 15))

    art_w = 600
    art = cover_art.resize((art_w, H), Image.LANCZOS)
    canvas.paste(art, (0, 0))

    draw = ImageDraw.Draw(canvas)
    font = _font(FONT_SEMIBOLD, 44)
    text_color, _ = get_font_for_background((15, 15, 15))
    _draw_wrapped_text(draw, caption, font, text_color, box=(art_w + 60, 80, W - 60, H - 80))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path


def render_linkedin(caption: str, cover_art: Image.Image, index: int, output_path: Path) -> Path:
    """
    LinkedIn (1200x627) — editorial. Subtle cover art background, bold centered text.
    """
    W, H = 1200, 627
    canvas = Image.new("RGB", (W, H), (15, 15, 15))

    art = cover_art.resize((W, H), Image.LANCZOS).convert("RGBA")
    darkened = Image.new("RGBA", (W, H), (15, 15, 15, 180))
    blended = Image.alpha_composite(art, darkened).convert("RGB")
    canvas.paste(blended, (0, 0))

    draw = ImageDraw.Draw(canvas)
    font = _font(FONT_SEMIBOLD, 42)
    text_color, _ = get_font_for_background((15, 15, 15))
    _draw_wrapped_text(draw, caption, font, text_color, box=(80, 60, W - 80, H - 60))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG")
    return output_path


# ── Dispatcher ────────────────────────────────────────────────────────────────

RENDERERS = {
    "ig_story":    render_story,
    "ig_portrait": render_portrait,
    "twitter":     render_twitter,
    "linkedin":    render_linkedin,
}


def generate_images(
    captions: dict[str, list[str]],
    cover_art_path: Path,
    output_dir: Path,
    episode_slug: str,
    selected_platforms: list[Platform],
) -> dict[str, list[Path]]:
    """
    Generate quote card images for each selected platform.
    Returns {platform_slug: [path1, path2, ...]}.
    Lazy-checks fonts on first call.
    """
    check_fonts()

    cover_art = Image.open(cover_art_path).convert("RGB")
    results: dict[str, list[Path]] = {}

    for platform in selected_platforms:
        slug = platform.slug
        renderer = RENDERERS[slug]
        platform_captions = captions.get(slug, [])
        paths = []

        for i, caption in enumerate(platform_captions):
            filename = f"{episode_slug}_{slug}_{i + 1:02d}.png"
            out_path = output_dir / slug / filename
            renderer(caption, cover_art, i, out_path)
            paths.append(out_path)

        results[slug] = paths

    return results


# ── Text utility ──────────────────────────────────────────────────────────────

def _draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    box: tuple,
) -> None:
    """Word-wrap and draw text within a bounding box."""
    x1, y1, x2, y2 = box
    max_width = x2 - x1
    words = text.split()
    lines = []
    line: list[str] = []

    for word in words:
        test = " ".join(line + [word])
        w = draw.textlength(test, font=font)
        if w <= max_width:
            line.append(word)
        else:
            if line:
                lines.append(" ".join(line))
            line = [word]
    if line:
        lines.append(" ".join(line))

    _, _, _, line_h = draw.textbbox((0, 0), "Ag", font=font)
    line_spacing = int(line_h * 1.4)
    y = y1

    for ln in lines:
        if y + line_h > y2:
            break
        draw.text((x1, y), ln, font=font, fill=color)
        y += line_spacing
