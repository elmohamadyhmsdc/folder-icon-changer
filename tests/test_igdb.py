from app.api import igdb


def test_escape_quotes_and_backslashes():
    raw = 'He said "hi"' + "\\"
    assert igdb._escape(raw) == 'He said \\"hi\\"' + "\\\\"
