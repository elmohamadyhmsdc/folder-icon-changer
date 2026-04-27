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
    badge_size = max(40, img.width // 6)
    badge = Image.new("RGBA", (badge_size, badge_size // 2 + 4), (0, 0, 0, 0))
    draw = ImageDraw.Draw(badge)
    draw.rounded_rectangle(
        [(0, 0), (badge_size - 1, badge_size // 2 + 3)],
        radius=6,
        fill=(20, 20, 20, 200),
    )
    text = f"★{score:.1f}"
    try:
        font_size = max(10, badge_size // 4)
        font = ImageFont.truetype("arial.ttf", font_size)
    except Exception:
        font = ImageFont.load_default()
    draw.text((4, 2), text, fill=(255, 215, 0, 255), font=font)

    result = img.copy()
    x = img.width - badge.width - 4
    y = img.height - badge.height - 4
    result.paste(badge, (x, y), badge)
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


def _compose(img: Image.Image, style: str, score: Optional[float], radius: int) -> Image.Image:
    img = img.convert("RGBA")
    size = img.size[0]  # assume square at this point

    if style == "clean_poster":
        if radius > 0:
            img = _apply_rounded_corners(img, radius)
    elif style == "framed":
        img = _add_border_frame(img)
        if radius > 0:
            img = _apply_rounded_corners(img, radius)
    elif style == "glassmorphism":
        img = _glassmorphism_frame(img)
        if radius > 0:
            img = _apply_rounded_corners(img, radius)
    elif style == "rating_badge":
        if radius > 0:
            img = _apply_rounded_corners(img, radius)
        img = _add_rating_badge(img, score)
    # "minimal" — no decorations

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

    # Crop to square (center crop)
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))

    # Resize to target
    img = img.resize((target_size, target_size), Image.LANCZOS)

    effective_style = "rating_badge" if show_badge else style
    img = _compose(img, effective_style, score, radius)

    # Build multi-resolution .ico
    sizes_to_embed = [s for s in _ICON_SIZES if s[0] <= target_size]
    resized_images = [img.resize(s, Image.LANCZOS) for s in sizes_to_embed]

    try:
        img.save(
            output_path,
            format="ICO",
            sizes=sizes_to_embed,
            append_images=resized_images[1:],
        )
        return True
    except Exception:
        return False
