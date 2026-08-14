"""GUI-Parität mit dem Budget-Tracker: selbst ausgelieferte Schriften und ein
dunkles Design nach Systemeinstellung."""
from fastapi.testclient import TestClient

from praemien_tracker.main import app

client = TestClient(app)


def _css() -> str:
    antwort = client.get("/static/css/style.css")
    assert antwort.status_code == 200
    return antwort.text


class TestSchriftenSelbstAusgeliefert:
    def test_kein_google_fonts(self):
        css = _css()
        assert "fonts.googleapis.com" not in css
        assert "fonts.gstatic.com" not in css

    def test_font_face_zeigt_auf_lokale_dateien(self):
        css = _css()
        assert "@font-face" in css
        assert "../fonts/inter-400.woff2" in css

    def test_font_datei_wird_ausgeliefert(self):
        antwort = client.get("/static/fonts/inter-400.woff2")
        assert antwort.status_code == 200
        assert antwort.content[:4] == b"wOF2"


class TestDarkMode:
    def test_media_query_vorhanden(self):
        assert "prefers-color-scheme: dark" in _css()

    def test_hero_nutzt_eigene_tokens(self):
        # Die Hero-Kachel darf nicht über --ink eingefärbt sein (wird im
        # dunklen Design hell) - sie nutzt eigene --hero-*-Tokens.
        css = _css()
        assert "--hero-bg" in css
        assert "background: var(--hero-bg)" in css
