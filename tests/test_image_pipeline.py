import pytest
from PIL import Image

from app.services import image_pipeline


@pytest.mark.parametrize("pref, largest", [(128, 128), (192, 128), (256, 256), (512, 256)])
def test_largest_ico_frame_matches_setting(tmp_path, monkeypatch, pref, largest):
    monkeypatch.setattr(image_pipeline, "_download_image", lambda url: Image.new("RGBA", (200, 300), (200, 30, 30, 255)))
    monkeypatch.setattr(image_pipeline, "load_prefs", lambda: {"icon_size": pref, "rounded_corners": False})
    out = tmp_path / "x.ico"
    assert image_pipeline.build_ico("http://example/x.png", str(out))
    sizes = Image.open(out).info["sizes"]
    assert max(sizes)[0] == largest
    assert (16, 16) in sizes
