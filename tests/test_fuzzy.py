import pytest

from app.utils.fuzzy import best_match, clean_title


@pytest.mark.parametrize("name, expected", [
    ("1917", "1917"),
    ("2012 (2009)", "2012"),
    ("Blade Runner 2049", "Blade Runner 2049"),
    ("2001 A Space Odyssey", "2001 A Space Odyssey"),
    ("Inception (2010) 1080p BluRay", "Inception"),
    ("Inception.2010.1080p.BluRay.x264", "Inception"),
    ("[SubGroup] Naruto [720p]", "Naruto"),
])
def test_clean_title(name, expected):
    assert clean_title(name) == expected


def test_clean_title_never_empty():
    assert clean_title("(2009)") != ""


def test_best_match_uses_all_titles():
    # Folder named after the romaji title must still match an entry that also has an English title.
    cands = [{"title": {"english": "Attack on Titan", "romaji": "Shingeki no Kyojin"}}]
    (_, score), = best_match("Shingeki no Kyojin", cands, ["title.english", "title.romaji"])
    assert score == 100.0


def test_best_match_sorted_and_limited():
    cands = [{"name": "Zelda"}, {"name": "Halo"}, {"name": "Halo 2"}]
    ranked = best_match("Halo", cands, ["name"], top_n=2)
    assert [c["name"] for c, _ in ranked][0] == "Halo"
    assert len(ranked) == 2
    assert ranked[0][1] >= ranked[1][1]


def test_best_match_empty():
    assert best_match("x", [], ["name"]) == []
