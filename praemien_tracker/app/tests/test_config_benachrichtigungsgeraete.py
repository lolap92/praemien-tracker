"""config._benachrichtigungsgeraete: kommagetrennte Geräteliste parsen."""

from __future__ import annotations

from praemien_tracker.config import _benachrichtigungsgeraete


def test_leer_ergibt_alle_geraete():
    assert _benachrichtigungsgeraete(None) == ["notify"]
    assert _benachrichtigungsgeraete("") == ["notify"]
    assert _benachrichtigungsgeraete("   ") == ["notify"]


def test_einzelnes_geraet():
    assert _benachrichtigungsgeraete("mobile_app_pixel_8") == ["mobile_app_pixel_8"]


def test_mehrere_geraete_kommagetrennt_und_getrimmt():
    assert _benachrichtigungsgeraete("mobile_app_pixel_8, mobile_app_iphone_anna") == [
        "mobile_app_pixel_8",
        "mobile_app_iphone_anna",
    ]


def test_leere_eintraege_zwischen_kommas_werden_uebersprungen():
    assert _benachrichtigungsgeraete("mobile_app_pixel_8,,  ,mobile_app_iphone_anna") == [
        "mobile_app_pixel_8",
        "mobile_app_iphone_anna",
    ]
