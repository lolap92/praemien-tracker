"""config._mydealz_gruppen: kommagetrennte Liste von mydealz-Gruppennamen
parsen - analog zu _benachrichtigungsgeraete/_dealdoktor_feed_urls."""

from __future__ import annotations

from praemien_tracker.config import _mydealz_gruppen


def test_leer_ergibt_die_vorgabegruppe():
    assert _mydealz_gruppen(None) == ["vertraege-finanzen"]
    assert _mydealz_gruppen("") == ["vertraege-finanzen"]
    assert _mydealz_gruppen("   ") == ["vertraege-finanzen"]


def test_einzelne_gruppe():
    assert _mydealz_gruppen("konto-kreditkarten") == ["konto-kreditkarten"]


def test_mehrere_gruppen_kommagetrennt_und_getrimmt():
    assert _mydealz_gruppen("vertraege-finanzen, konto-kreditkarten") == [
        "vertraege-finanzen",
        "konto-kreditkarten",
    ]


def test_leere_eintraege_zwischen_kommas_werden_uebersprungen():
    assert _mydealz_gruppen("vertraege-finanzen,,  ,konto-kreditkarten") == [
        "vertraege-finanzen",
        "konto-kreditkarten",
    ]
