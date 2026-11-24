import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from PIL import Image

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# Expected locations of the waifu2x binary (project root or app/resources)
_BINARY_CANDIDATES = [
    _PROJECT_ROOT / "resources" / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan.exe",
    _PROJECT_ROOT / "app" / "resources" / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan.exe",
    Path("resources") / "waifu2x-ncnn-vulkan" / "waifu2x-ncnn-vulkan.exe",
]


def _find_binary() -> Optional[str]:
    for p in _BINARY_CANDIDATES:
        if p.exists():
            return str(p)
    return None


def _lanczos(img: Image.Image, scale: int) -> Image.Image:
    w, h = img.size
    return img.resize((w * scale, h * scale), Image.LANCZOS)


def upscale(img: Image.Image, scale: int = 2, noise: int = 2) -> Image.Image:
    """
    Upscale an image using waifu2x (anime-optimised).
    Falls back to Pillow LANCZOS if waifu2x is not available.

    scale: 1, 2, or 4
    noise: 0–3 (noise reduction level; 2 is good for compressed web images)
    """
    binary = _find_binary()
    if binary is None:
        return _lanczos(img, scale)

    with tempfile.TemporaryDirectory() as tmp:
        inp = os.path.join(tmp, "input.png")
        out = os.path.join(tmp, "output.png")
        model_dir = str(Path(binary).parent / "models-cunet")

        img.save(inp, format="PNG")
        cmd = [
            binary,
            "-i", inp,
            "-o", out,
            "-s", str(scale),
            "-n", str(noise),
            "-m", model_dir,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            return Image.open(out).copy()
        except Exception:
            # Any failure → LANCZOS fallback
            return _lanczos(img, scale)
