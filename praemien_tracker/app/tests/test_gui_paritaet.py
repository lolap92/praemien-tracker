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

    def test_ausdrueckliche_wahl_uebersteuert_system(self):
        # Beide Richtungen: erzwungenes Dunkel und System-Dunkel-mit-Ausnahme.
        css = _css()
        assert ':root[data-theme="dark"]' in css
        assert ':root:not([data-theme="light"])' in css

    def test_umschalter_ist_da(self):
        html = client.get("/overview").text
        assert 'id="theme-toggle"' in html
        assert "pt-theme" in html  # localStorage-Schlüssel im Kopf-/Fußskript


class TestRedirectHaertung:
    def test_protokollrelatives_ziel_wird_verworfen(self):
        from starlette.requests import Request

        from praemien_tracker.ingress import redirect

        req = Request({"type": "http", "headers": []})
        antwort = redirect(req, "//example.com/pwned")
        assert antwort.headers["location"] == "/overview"

    def test_internes_ziel_bleibt(self):
        from starlette.requests import Request

        from praemien_tracker.ingress import redirect

        req = Request({"type": "http", "headers": []})
        assert redirect(req, "deals").headers["location"] == "/deals"
