"""config._benachrichtigungsgeraete: kommagetrennte Geräteliste parsen."""

from __future__ import annotations

from praemien_tracker.config import _benachrichtigungsgeraete


def test_leer_ergibt_alle_geraete():
    assert _benachrichtigungsgeraete(None) == ["sm_g990b", "sm_g990u", "fp5"]
    assert _benachrichtigungsgeraete("") == ["sm_g990b", "sm_g990u", "fp5"]
    assert _benachrichtigungsgeraete("   ") == ["sm_g990b", "sm_g990u", "fp5"]


def test_einzelnes_geraet():
    assert _benachrichtigungsgeraete("sm_g990b") == ["sm_g990b"]


def test_mehrere_geraete_kommagetrennt_und_getrimmt():
    assert _benachrichtigungsgeraete("sm_g990b, fp5") == [
        "sm_g990b",
        "fp5",
    ]


def test_leere_eintraege_zwischen_kommas_werden_uebersprungen():
    assert _benachrichtigungsgeraete("sm_g990b,,  ,fp5") == [
        "sm_g990b",
        "fp5",
    ]
