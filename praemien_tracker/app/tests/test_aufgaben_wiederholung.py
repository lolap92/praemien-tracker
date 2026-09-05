"""Monatlich wiederkehrende manuelle Aufgaben und der Zeitraum-Filter im
Reiter "Zu erledigen".

Eine monatliche Aufgabe verschiebt beim Abhaken nicht ihr eigenes Datum,
sondern legt eine neue Zeile für den Folgemonat an - die erledigte bleibt als
Fakt bestehen (siehe models.Aufgabe). Genau das prüfen die Tests hier, dazu
den Rückweg (Wiederöffnen) und die Trennung "jetzt fällig" vs. "später".
"""

from __future__ import annotations

import datetime

from fastapi.testclient import TestClient

from praemien_tracker import derived
from praemien_tracker.main import app
from praemien_tracker.models import Aufgabe

client = TestClient(app)

HEUTE = datetime.date.today()


def _aufgaben(db) -> list[Aufgabe]:
    return db.query(Aufgabe).order_by(Aufgabe.id).all()


# --- Terminberechnung (derived) ---


def test_naechster_monatstermin_behaelt_den_tag_im_monat():
    """"Immer zum Ersten" soll der Erste bleiben, nicht zum Abhak-Tag
    wandern."""
    termin = derived.naechster_monatstermin(datetime.date(2026, 3, 1), heute=datetime.date(2026, 3, 17))
    assert termin == datetime.date(2026, 4, 1)


def test_naechster_monatstermin_ueberspringt_verstrichene_monate():
    """Eine lange liegengebliebene Aufgabe darf nicht sofort wieder überfällig
    sein - es werden so viele Monate addiert, bis der Termin in der Zukunft
    liegt."""
    termin = derived.naechster_monatstermin(datetime.date(2026, 1, 10), heute=datetime.date(2026, 4, 20))
    assert termin == datetime.date(2026, 5, 10)


def test_naechster_monatstermin_kuerzt_auf_die_monatslaenge():
    termin = derived.naechster_monatstermin(datetime.date(2026, 1, 31), heute=datetime.date(2026, 1, 31))
    assert termin == datetime.date(2026, 2, 28)


def test_naechster_monatstermin_ohne_datum_ankert_auf_heute():
    termin = derived.naechster_monatstermin(None, heute=datetime.date(2026, 3, 15))
    assert termin == datetime.date(2026, 4, 15)


def test_unbekannte_wiederholung_gilt_als_einmalig():
    """Sonst schriebe sich eine Aufgabe mit unlesbarem Wert endlos fort."""
    assert derived.normalisiere_wiederholung("quartalsweise") == derived.WIEDERHOLUNG_EINMALIG
    assert derived.normalisiere_wiederholung(None) == derived.WIEDERHOLUNG_EINMALIG
    assert derived.normalisiere_wiederholung("Monatlich") == derived.WIEDERHOLUNG_MONATLICH


# --- Anlegen ---


def test_monatliche_aufgabe_ohne_frist_ankert_auf_heute(db):
    """Ohne Datum gäbe es keinen nächsten Termin - die Kette braucht einen
    Anker."""
    antwort = client.post(
        "/todos/aufgaben",
        data={"beschreibung": "Kontoauszüge prüfen", "wiederholung": "monatlich"},
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    (aufgabe,) = _aufgaben(db)
    assert aufgabe.wiederholung == "monatlich"
    assert aufgabe.faellig_bis == HEUTE


def test_einmalige_aufgabe_bleibt_ohne_frist(db):
    client.post("/todos/aufgaben", data={"beschreibung": "Einmal etwas"}, follow_redirects=False)
    (aufgabe,) = _aufgaben(db)
    assert aufgabe.wiederholung == "einmalig"
    assert aufgabe.faellig_bis is None


# --- Abhaken und Rückweg ---


def test_abhaken_legt_den_folgetermin_an(db):
    db.add(
        Aufgabe(
            beschreibung="Kontoauszüge prüfen",
            faellig_bis=HEUTE,
            wiederholung=derived.WIEDERHOLUNG_MONATLICH,
        )
    )
    db.commit()
    original = _aufgaben(db)[0]

    client.post(f"/todos/aufgaben/{original.id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()

    erledigt, nachfolger = _aufgaben(db)
    assert erledigt.erledigt is True
    assert nachfolger.erledigt is False
    assert nachfolger.beschreibung == "Kontoauszüge prüfen"
    assert nachfolger.wiederholung == derived.WIEDERHOLUNG_MONATLICH
    assert nachfolger.vorgaenger_id == erledigt.id
    assert nachfolger.faellig_bis == derived.naechster_monatstermin(HEUTE)


def test_einmalige_aufgabe_legt_keinen_folgetermin_an(db):
    db.add(Aufgabe(beschreibung="Einmal etwas", faellig_bis=HEUTE))
    db.commit()
    original = _aufgaben(db)[0]

    client.post(f"/todos/aufgaben/{original.id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()

    assert len(_aufgaben(db)) == 1


def test_wieder_oeffnen_nimmt_den_folgetermin_zurueck(db):
    """Ein versehentliches Abhaken darf keine Dublette hinterlassen."""
    db.add(Aufgabe(beschreibung="Monatlich", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH))
    db.commit()
    original_id = _aufgaben(db)[0].id

    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()
    assert len(_aufgaben(db)) == 2

    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "off"}, follow_redirects=False)
    db.expire_all()

    (uebrig,) = _aufgaben(db)
    assert uebrig.id == original_id
    assert uebrig.erledigt is False


def test_wieder_oeffnen_laesst_bereits_erledigten_folgetermin_stehen(db):
    """Ist der Folgetermin selbst schon abgehakt, gehört er zur Historie - er
    darf nicht rückwirkend verschwinden."""
    db.add(Aufgabe(beschreibung="Monatlich", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH))
    db.commit()
    original_id = _aufgaben(db)[0].id

    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()
    nachfolger_id = _aufgaben(db)[1].id
    client.post(f"/todos/aufgaben/{nachfolger_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()

    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "off"}, follow_redirects=False)
    db.expire_all()

    ids = [a.id for a in _aufgaben(db)]
    assert nachfolger_id in ids


def test_zweites_abhaken_erzeugt_keinen_zweiten_folgetermin(db):
    """Abhaken, wieder öffnen (Folgetermin weg), nochmal abhaken: es darf
    trotzdem nur einer entstehen."""
    db.add(Aufgabe(beschreibung="Monatlich", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH))
    db.commit()
    original_id = _aufgaben(db)[0].id

    for wert in ("on", "off", "on"):
        client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": wert}, follow_redirects=False)
        db.expire_all()

    offene = [a for a in _aufgaben(db) if not a.erledigt]
    assert len(offene) == 1


def test_loeschen_beendet_die_reihe(db):
    """Wer die Aufgabe löscht, will die Reihe beenden - ein offener
    Folgetermin darf nicht als Waise weiterleben."""
    db.add(Aufgabe(beschreibung="Monatlich", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH))
    db.commit()
    original_id = _aufgaben(db)[0].id
    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()

    client.post(f"/todos/aufgaben/{original_id}/delete", follow_redirects=False)
    db.expire_all()

    assert _aufgaben(db) == []


# --- Zeitraum-Filter ---


def _anlegen(db, beschreibung: str, faellig_bis: datetime.date | None) -> None:
    db.add(Aufgabe(beschreibung=beschreibung, faellig_bis=faellig_bis))
    db.commit()


def test_spaetere_aufgabe_ist_standardmaessig_ausgeblendet(db):
    _anlegen(db, "Jetzt fällig", HEUTE)
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))

    html = client.get("/todos?tab=manuell").text
    assert "Jetzt fällig" in html
    assert "Erst nächsten Monat" not in html


def test_filter_zeigt_nur_spaetere_aufgaben(db):
    _anlegen(db, "Jetzt fällig", HEUTE)
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))

    html = client.get("/todos?tab=manuell&faellig=zukuenftig").text
    assert "Erst nächsten Monat" in html
    assert "Jetzt fällig" not in html


def test_filter_alle_zeigt_beide(db):
    _anlegen(db, "Jetzt fällig", HEUTE)
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))

    html = client.get("/todos?tab=manuell&faellig=alle").text
    assert "Erst nächsten Monat" in html
    assert "Jetzt fällig" in html


def test_unbekannter_filterwert_faellt_auf_aktuell_zurueck(db):
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))
    html = client.get("/todos?tab=manuell&faellig=irgendwas").text
    assert "Erst nächsten Monat" not in html


def test_ueberfaellige_aufgabe_gilt_als_aktuell(db):
    """"Aktuell" heißt "spätestens jetzt", nicht "genau heute"."""
    _anlegen(db, "Längst fällig", HEUTE - datetime.timedelta(days=10))
    html = client.get("/todos?tab=manuell").text
    assert "Längst fällig" in html


def test_aufgabe_ohne_frist_gilt_als_aktuell(db):
    _anlegen(db, "Ohne Frist", None)
    html = client.get("/todos?tab=manuell").text
    assert "Ohne Frist" in html


# --- Startseite und Statistiken ---


def test_spaetere_aufgabe_steht_nicht_unter_jetzt_dran(db):
    """Was erst nächsten Monat ansteht, ist keine Aufgabe für heute."""
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))
    html = client.get("/overview").text
    assert "Eigene Aufgaben" not in html
    assert "Nichts zu tun" in html


def test_statistiken_zaehlen_spaetere_aufgaben_getrennt(db):
    _anlegen(db, "Jetzt fällig", HEUTE)
    _anlegen(db, "Erst nächsten Monat", HEUTE + datetime.timedelta(days=30))

    html = client.get("/statistiken").text
    assert "Aufgaben mit späterem Termin" in html
    assert 'href="todos?tab=manuell&amp;faellig=zukuenftig"' in html


def test_deal_loeschen_raeumt_eine_aufgabenkette_mit_ab(db):
    """Eine monatliche Aufgabe an einem Deal bildet eine Kette von Zeilen, die
    alle am selben Deal hängen. Beim Löschen des Deals müssen sie in der
    richtigen Reihenfolge verschwinden - sonst scheitert der Fremdschlüssel
    des Nachfolgers auf seinen Vorgänger."""
    from praemien_tracker.models import Bank, Deal, Inhaber

    deal = Deal(kontoart="Girokonto", bank=Bank(name="Kettenbank"), inhaber=Inhaber(name="Max"))
    deal.aufgaben.append(
        Aufgabe(beschreibung="Monatlich am Deal", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH)
    )
    db.add(deal)
    db.commit()
    deal_id = deal.id
    aufgabe_id = deal.aufgaben[0].id

    client.post(f"/todos/aufgaben/{aufgabe_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()
    assert len(_aufgaben(db)) == 2

    antwort = client.post(f"/deals/{deal_id}/delete", follow_redirects=False)
    assert antwort.status_code == 303
    db.expire_all()
    assert _aufgaben(db) == []


# --- Bearbeiten ---


def test_bearbeiten_aendert_text_frist_und_wiederholung(db):
    db.add(Aufgabe(beschreibung="Alter Text", faellig_bis=HEUTE))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    antwort = client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={
            "beschreibung": "Neuer Text",
            "faellig_bis": "2026-12-01",
            "wiederholung": "monatlich",
            "tab": "manuell",
        },
        follow_redirects=False,
    )
    assert antwort.status_code == 303
    db.expire_all()

    (aufgabe,) = _aufgaben(db)
    assert aufgabe.beschreibung == "Neuer Text"
    assert aufgabe.faellig_bis == datetime.date(2026, 12, 1)
    assert aufgabe.wiederholung == derived.WIEDERHOLUNG_MONATLICH


def test_bearbeiten_kann_den_deal_setzen_und_wieder_loesen(db):
    from praemien_tracker.models import Bank, Deal, Inhaber

    deal = Deal(kontoart="Girokonto", bank=Bank(name="Zuordnungsbank"), inhaber=Inhaber(name="Max"))
    db.add(deal)
    db.add(Aufgabe(beschreibung="Allgemein"))
    db.commit()
    deal_id = deal.id
    aufgabe_id = _aufgaben(db)[0].id

    client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "Allgemein", "deal_id": str(deal_id)},
        follow_redirects=False,
    )
    db.expire_all()
    assert _aufgaben(db)[0].deal_id == deal_id

    client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "Allgemein", "deal_id": ""},
        follow_redirects=False,
    )
    db.expire_all()
    assert _aufgaben(db)[0].deal_id is None


def test_bearbeiten_auf_monatlich_ohne_frist_ankert_auf_heute(db):
    """Dieselbe Regel wie beim Anlegen - ohne Datum gäbe es keinen nächsten
    Termin."""
    db.add(Aufgabe(beschreibung="Ohne Frist"))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "Ohne Frist", "wiederholung": "monatlich"},
        follow_redirects=False,
    )
    db.expire_all()
    assert _aufgaben(db)[0].faellig_bis == HEUTE


def test_bearbeiten_kann_die_frist_wieder_entfernen(db):
    db.add(Aufgabe(beschreibung="Mit Frist", faellig_bis=HEUTE))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "Mit Frist", "faellig_bis": "", "wiederholung": "einmalig"},
        follow_redirects=False,
    )
    db.expire_all()
    assert _aufgaben(db)[0].faellig_bis is None


def test_bearbeiten_mit_leerer_beschreibung_laesst_den_text_stehen(db):
    """Eine Aufgabe ohne Text wäre in der Liste nicht wiederzuerkennen."""
    db.add(Aufgabe(beschreibung="Bleibt stehen"))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "   "},
        follow_redirects=False,
    )
    db.expire_all()
    assert _aufgaben(db)[0].beschreibung == "Bleibt stehen"


def test_bearbeiten_laesst_einen_bestehenden_folgetermin_unveraendert(db):
    """Der Folgetermin ist aus dem damaligen Stand hervorgegangen und wird
    nicht rückwirkend umgeschrieben."""
    db.add(Aufgabe(beschreibung="Monatlich", faellig_bis=HEUTE, wiederholung=derived.WIEDERHOLUNG_MONATLICH))
    db.commit()
    original_id = _aufgaben(db)[0].id
    client.post(f"/todos/aufgaben/{original_id}/toggle", data={"wert": "on"}, follow_redirects=False)
    db.expire_all()
    nachfolger = _aufgaben(db)[1]
    nachfolger_text, nachfolger_datum = nachfolger.beschreibung, nachfolger.faellig_bis

    client.post(
        f"/todos/aufgaben/{original_id}/bearbeiten",
        data={"beschreibung": "Umbenannt", "faellig_bis": "2027-01-01", "wiederholung": "monatlich"},
        follow_redirects=False,
    )
    db.expire_all()

    unveraendert = _aufgaben(db)[1]
    assert unveraendert.beschreibung == nachfolger_text
    assert unveraendert.faellig_bis == nachfolger_datum


def test_bearbeiten_einer_unbekannten_aufgabe_ist_kein_fehler(db):
    antwort = client.post(
        "/todos/aufgaben/9999/bearbeiten", data={"beschreibung": "Egal"}, follow_redirects=False
    )
    assert antwort.status_code == 303


def test_offene_aufgabe_laesst_sich_loeschen(db):
    """Bisher gab es den Löschen-Knopf nur bei erledigten Aufgaben - eine
    vertippte offene Aufgabe musste erst abgehakt werden."""
    db.add(Aufgabe(beschreibung="Versehen"))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    client.post(f"/todos/aufgaben/{aufgabe_id}/delete", data={"tab": "manuell"}, follow_redirects=False)
    db.expire_all()
    assert _aufgaben(db) == []


def test_bearbeiten_dialog_steht_im_reiter(db):
    db.add(Aufgabe(beschreibung="Bearbeitbar"))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    html = client.get("/todos?tab=manuell").text
    assert f'id="dlg-aufgabe-{aufgabe_id}"' in html
    assert f'action="todos/aufgaben/{aufgabe_id}/bearbeiten"' in html


def test_speichern_mit_zukunftsdatum_schaltet_den_filter_auf_alle(db):
    """Sonst wäre die Aufgabe nach dem Speichern schlicht verschwunden - sie
    fällt aus der Voreinstellung "aktuell fällig" heraus."""
    db.add(Aufgabe(beschreibung="Wandert in die Zukunft", faellig_bis=HEUTE))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    antwort = client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={
            "beschreibung": "Wandert in die Zukunft",
            "faellig_bis": (HEUTE + datetime.timedelta(days=40)).isoformat(),
            "tab": "manuell",
        },
        follow_redirects=False,
    )
    assert "faellig=alle" in antwort.headers["location"]


def test_speichern_ohne_zukunftsdatum_laesst_den_filter_in_ruhe(db):
    db.add(Aufgabe(beschreibung="Bleibt aktuell", faellig_bis=HEUTE))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    antwort = client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={"beschreibung": "Bleibt aktuell", "faellig_bis": HEUTE.isoformat(), "tab": "manuell"},
        follow_redirects=False,
    )
    assert "faellig=" not in antwort.headers["location"]


def test_bewusst_gesetzter_filter_bleibt_beim_speichern_erhalten(db):
    db.add(Aufgabe(beschreibung="Spätere Aufgabe", faellig_bis=HEUTE + datetime.timedelta(days=40)))
    db.commit()
    aufgabe_id = _aufgaben(db)[0].id

    antwort = client.post(
        f"/todos/aufgaben/{aufgabe_id}/bearbeiten",
        data={
            "beschreibung": "Spätere Aufgabe",
            "faellig_bis": (HEUTE + datetime.timedelta(days=40)).isoformat(),
            "tab": "manuell",
            "faellig": "zukuenftig",
        },
        follow_redirects=False,
    )
    assert "faellig=zukuenftig" in antwort.headers["location"]


def test_neue_aufgabe_mit_spaeterer_frist_bleibt_sichtbar(db):
    antwort = client.post(
        "/todos/aufgaben",
        data={
            "beschreibung": "Erst im nächsten Monat",
            "faellig_bis": (HEUTE + datetime.timedelta(days=40)).isoformat(),
        },
        follow_redirects=False,
    )
    assert "faellig=alle" in antwort.headers["location"]
