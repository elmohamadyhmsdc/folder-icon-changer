import io
import os
import tempfile
from typing import Optional, Tuple

import requests
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.config import load_prefs
from app.services.detector import ContentType
from app.utils import cache as _cache
from app.utils import upscaler


_ICON_SIZES = [(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)]


def _download_image(url: str) -> Optional[Image.Image]:
    """Download an image from a URL, using disk cache."""
    cached_path = _cache.get_image_path(url)
    if cached_path and os.path.exists(cached_path):
        return Image.open(cached_path).convert("RGBA")

    try:
        resp = requests.get(url, stream=True, timeout=15)
        resp.raise_for_status()
        data = resp.content
        img = Image.open(io.BytesIO(data)).convert("RGBA")

        # Persist to cache directory
        from app.config import cache_dir
        import hashlib
        fname = hashlib.md5(url.encode()).hexdigest() + ".png"
        local_path = os.path.join(cache_dir(), fname)
        img.save(local_path, format="PNG")
        _cache.set_image_path(url, local_path)
        return img
    except Exception:
        return None


def _apply_rounded_corners(img: Image.Image, radius: int) -> Image.Image:
    mask = Image.new("L", img.size, 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle([(0, 0), img.size], radius=radius, fill=255)
    result = img.copy()
    result.putalpha(mask)
    return result


def _add_rating_badge(img: Image.Image, score: Optional[float]) -> Image.Image:
    if score is None:
        return img
    size = img.width  # square canvas at this point
    badge_w = max(52, int(size * 0.22))
    badge_h = max(22, int(badge_w * 0.42))
    font_size = max(12, int(badge_h * 0.64))

    badge = Image.new("RGBA", (badge_w, badge_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    # Fully-rounded pill, semi-transparent dark background
    draw.rounded_rectangle(
        [(0, 0), (badge_w - 1, badge_h - 1)],
        radius=badge_h // 2,
        fill=(12, 12, 12, 190),
    )
    # Segoe UI Symbol ships on every Windows 10/11 machine and correctly renders ★ (U+2605).
    # Arial does NOT include it and shows □ instead, so we try Segoe first.
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont
    for name in ("seguisym.ttf", "segoeui.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            font = ImageFont.truetype(name, font_size)
            break
        except Exception:
            pass
    else:
        font = ImageFont.load_default()

    text = f"★ {score:.1f}"
    # Centre the text inside the pill
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = (badge_w - tw) // 2 - bbox[0]
    ty = (badge_h - th) // 2 - bbox[1]
    draw.text((tx, ty), text, fill=(255, 255, 255, 245), font=font)

    result = img.copy()
    margin = max(6, int(size * 0.035))
    result.paste(badge, (size - badge_w - margin, size - badge_h - margin), badge)
    return result


def _add_border_frame(img: Image.Image, color: Tuple = (255, 255, 255), thickness: int = 6) -> Image.Image:
    draw = ImageDraw.Draw(img)
    draw.rectangle(
        [(thickness // 2, thickness // 2), (img.width - thickness // 2, img.height - thickness // 2)],
        outline=color + (255,),
        width=thickness,
    )
    return img


def _glassmorphism_frame(img: Image.Image) -> Image.Image:
    border = Image.new("RGBA", img.size, (0, 0, 0, 0))
    blurred = img.filter(ImageFilter.GaussianBlur(radius=8))
    border.paste(blurred)
    draw = ImageDraw.Draw(border)
    t = 10
    draw.rectangle([(0, 0), (img.width - 1, img.height - 1)], outline=(255, 255, 255, 60), width=t)
    result = Image.alpha_composite(border, img)
    return result


def _fit_to_square(img: Image.Image, size: int) -> Image.Image:
    """
    Compose the poster onto a blurred, darkened backdrop so the full artwork
    is visible — the same technique used by Netflix, Spotify, and Apple Music.

    Background layer: poster scaled to fill the square (cover), heavily
    blurred and darkened.
    Foreground layer: poster scaled to fit within the square (contain),
    centred with a slight upward bias so titles/faces stay prominent.
    """
    img = img.convert("RGBA")
    w, h = img.size

    # --- Background: cover-scale → blur → darken ---
    bg_scale = max(size / w, size / h)
    bg_w, bg_h = int(w * bg_scale), int(h * bg_scale)
    bg = img.resize((bg_w, bg_h), Image.LANCZOS)
    # Centre-crop to exact square
    bx = (bg_w - size) // 2
    by = (bg_h - size) // 2
    bg = bg.crop((bx, by, bx + size, by + size))
    # Blur and darken
    bg = bg.filter(ImageFilter.GaussianBlur(radius=18))
    r, g, b, a = bg.split()
    darken = 0.5
    r = r.point(lambda x: int(x * darken))
    g = g.point(lambda x: int(x * darken))
    b = b.point(lambda x: int(x * darken))
    bg = Image.merge("RGBA", (r, g, b, a))

    # --- Foreground: contain-scale, slight upward bias ---
    fg_scale = min(size / w, size / h)
    fg_w, fg_h = int(w * fg_scale), int(h * fg_scale)
    fg = img.resize((fg_w, fg_h), Image.LANCZOS)
    # Centre horizontally; shift slightly upward (30% of vertical slack)
    paste_x = (size - fg_w) // 2
    slack_y = size - fg_h
    paste_y = int(slack_y * 0.30)
    bg.paste(fg, (paste_x, paste_y), fg)

    return bg


def _compose(img: Image.Image, style: str, radius: int) -> Image.Image:
    """Apply the chosen frame decoration (rounded corners, border, glassmorphism).
    Badge overlay is handled separately in build_ico."""
    img = img.convert("RGBA")

    if style == "framed":
        img = _add_border_frame(img)
    elif style == "glassmorphism":
        img = _glassmorphism_frame(img)
    # clean_poster, minimal, rating_badge → no extra frame decoration

    if radius > 0 and style != "minimal":
        img = _apply_rounded_corners(img, radius)

    return img


def build_ico(
    image_url: str,
    output_path: str,
    content_type: ContentType = ContentType.UNKNOWN,
    score: Optional[float] = None,
) -> bool:
    """
    Full pipeline: download → maybe upscale → compose style → save .ico.
    Returns True on success.
    """
    prefs = load_prefs()
    style = prefs.get("icon_style", "clean_poster")
    radius = prefs.get("corner_radius", 12) if prefs.get("rounded_corners", True) else 0
    show_badge = prefs.get("show_rating_badge", False)
    do_upscale = prefs.get("upscale_anime", True)
    target_size = prefs.get("icon_size", 256)

    img = _download_image(image_url)
    if img is None:
        return False

    # Upscale low-res anime images
    if do_upscale and content_type == ContentType.ANIME and img.width < 300:
        scale = 4 if img.width < 150 else 2
        img = upscaler.upscale(img, scale=scale, noise=2)

    # Fit poster into square canvas with blurred background fill
    img = _fit_to_square(img, target_size)

    img = _compose(img, style, radius)
    # Badge is applied if the checkbox is on OR if "Rating Badge" is the chosen style
    if show_badge or style == "rating_badge":
        img = _add_rating_badge(img, score)

    # Build multi-resolution .ico — explicit per-size images (Pillow ICO requirement)
    sizes_to_embed = [s for s in _ICON_SIZES if s[0] <= target_size]
    frames = [img.resize(s, Image.LANCZOS).convert("RGBA") for s in sizes_to_embed]

    try:
        # Save largest first, append smaller — Pillow ICO requires largest as the base
        frames[0].save(output_path, format="ICO", append_images=frames[1:])
        return True
    except Exception:
        return False
