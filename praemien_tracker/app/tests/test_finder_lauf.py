"""finder/lauf.py: der komplette Durchlauf, mit Fake-Anthropic-Client und
gepatchten Quellen (kein Netzwerk)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest

from praemien_tracker import config
from praemien_tracker.finder import lauf, matching, notify
from praemien_tracker.finder.extraktion import AngebotExtraktion, BedingungExtraktion, RelevanzErgebnis
from praemien_tracker.finder.quellen import RohFund
from praemien_tracker.models import DealVorschlag, FinderFund, FinderLauf, Inhaber


class FakeMessages:
    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.relevanz = relevanz
        self.extraktion = extraktion

    def parse(self, *, output_format, **kwargs):
        if output_format is RelevanzErgebnis:
            return SimpleNamespace(parsed_output=self.relevanz, stop_reason="end_turn")
        return SimpleNamespace(parsed_output=self.extraktion, stop_reason="end_turn")


class FakeClient:
    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.messages = FakeMessages(relevanz, extraktion)


class ZaehlenderFakeClient:
    """Wie FakeClient, zählt aber jeden Aufruf von messages.parse - damit
    sich prüfen lässt, ob der Cache einen API-Aufruf tatsächlich einspart."""

    def __init__(self, relevanz: RelevanzErgebnis, extraktion: AngebotExtraktion | None):
        self.relevanz = relevanz
        self.extraktion = extraktion
        self.aufrufe = 0
        self.messages = self

    def parse(self, *, output_format, **kwargs):
        self.aufrufe += 1
        if output_format is RelevanzErgebnis:
            return SimpleNamespace(parsed_output=self.relevanz, stop_reason="end_turn")
        return SimpleNamespace(parsed_output=self.extraktion, stop_reason="end_turn")


@pytest.fixture()
def zwei_inhaber(db):
    """Zwei erwachsene Inhaber - der Lauf legt je Inhaber eine eigene Zeile an
    (siehe finder/lauf.py). Namen sind frei erfundene Test-Platzhalter."""
    alice = Inhaber(name="Alice")
    bob = Inhaber(name="Bob")
    db.add_all([alice, bob])
    db.commit()
    return [alice, bob]


def _patch_quellen(monkeypatch, funde: list[RohFund]) -> None:
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: funde)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])


def test_lauf_ohne_client_tut_nichts(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf.config, "ANTHROPIC_API_KEY", None)
    zaehler = lauf.taeglicher_lauf(db)
    assert zaehler["gefunden"] == 0
    assert db.query(DealVorschlag).count() == 0


def test_lauf_legt_pro_inhaber_eine_zeile_an(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "C24 125 Euro", "Neukunden erhalten 125 Euro.")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 2  # zwei Zeilen (eine je Inhaber)
    assert zaehler["neue_vorschlaege"] == 1  # aber nur ein neues Angebot / eine Karte
    assert zaehler[matching.STATUS_VORGESCHLAGEN] == 2
    zeilen = db.query(DealVorschlag).all()
    inhaber_namen = {z.inhaber.name for z in zeilen}
    assert inhaber_namen == {"Alice", "Bob"}


def test_minderjaehrige_bekommen_nur_kinderdeals(db, monkeypatch):
    """Einem minderjährigen Inhaber wird ein Angebot nur vorgeschlagen, wenn es
    laut Extraktion (auch) für Kinder abschließbar ist (fuer_kinder=True).
    Reine Erwachsenen-Angebote (Default fuer_kinder=False) erscheinen für das
    Kind gar nicht - der Erwachsene bekommt sie normal."""
    erwachsen = Inhaber(name="Alice")
    kind = Inhaber(name="Kim", ist_minderjaehrig=True)
    db.add_all([erwachsen, kind])
    db.commit()

    # Eindeutiger Marker im Rohtext (der Extraktions-Prompt selbst nennt
    # "Junior-Depot" als Beispiel - deshalb ein Token, das nur im Fund steht).
    erwachsenen_deal = RohFund("mydealz", "https://mydealz.de/giro", "t", "nur Erwachsene")
    kinder_deal = RohFund("mydealz", "https://mydealz.de/junior", "t", "Angebot MARKER_KIND fuer Junge")
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [erwachsenen_deal, kinder_deal])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])

    class NachTextMessages:
        def parse(self, *, output_format, messages, **kwargs):
            text = messages[-1]["content"] if messages else ""
            if output_format is RelevanzErgebnis:
                return SimpleNamespace(parsed_output=RelevanzErgebnis(ist_relevant=True), stop_reason="end_turn")
            ist_kinder = "MARKER_KIND" in text
            return SimpleNamespace(
                parsed_output=AngebotExtraktion(
                    bank_name="Bank", kontoart="Depot" if ist_kinder else "Girokonto",
                    praemie_betrag=125.0, fuer_kinder=ist_kinder, bedingungen=[],
                ),
                stop_reason="end_turn",
            )

    class NachTextClient:
        messages = NachTextMessages()

    lauf.taeglicher_lauf(db, client=NachTextClient())

    zeilen = db.query(DealVorschlag).all()
    # Erwachsener: beide Deals. Kind: nur der Junior-Deal.
    erwachsenen_urls = {z.quelle_url for z in zeilen if z.inhaber_id == erwachsen.id}
    kind_urls = {z.quelle_url for z in zeilen if z.inhaber_id == kind.id}
    assert erwachsenen_urls == {"https://mydealz.de/giro", "https://mydealz.de/junior"}
    assert kind_urls == {"https://mydealz.de/junior"}


def test_stehen_gebliebene_kinder_vorschlaege_werden_bei_reinem_erwachsenen_deal_geloescht(
    db, monkeypatch
):
    """Regressionstest: eine für ein minderjähriges Kind schon bestehende,
    noch offene Vorschlagszeile (z.B. angelegt, bevor es die Alterprüfung
    gab, oder unter einer damals abweichenden fuer_kinder-Einschätzung) darf
    nicht für immer offen hängen bleiben - sonst bliebe die Vorschlags-Karte
    trotz Übernahme durch alle Erwachsenen sichtbar (siehe
    _nicht_anwendbaren_vorschlag_entfernen). Sie wird beim nächsten Lauf
    automatisch gelöscht (nicht verworfen - für das Kind gibt es dabei
    weder etwas zu übernehmen noch zu verwerfen, siehe Docstring dort)."""
    erwachsen = Inhaber(name="Alice")
    kind = Inhaber(name="Kim", ist_minderjaehrig=True)
    db.add_all([erwachsen, kind])
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/giro", "t", "nur Erwachsene")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Bank", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    # Stehen gebliebene Alt-Zeile für das Kind, wie sie vor Einführung der
    # Alterprüfung entstanden wäre - noch offen ("vorgeschlagen").
    alte_kind_zeile = DealVorschlag(
        inhaber_id=kind.id,
        quelle="mydealz",
        quelle_url=fund.quelle_url,
        bank_name="Bank",
        kontoart="Girokonto",
        praemie_betrag=125.0,
        roh_json="{}",
        inhalt_hash="alt-hash",
        status=matching.STATUS_VORGESCHLAGEN,
    )
    db.add(alte_kind_zeile)
    db.commit()
    kind_zeile_id = alte_kind_zeile.id

    lauf.taeglicher_lauf(db, client=client)

    db.expire_all()
    assert db.get(DealVorschlag, kind_zeile_id) is None

    # Die Erwachsenen-Zeile ist normal neu entstanden und offen.
    erwachsenen_zeile = (
        db.query(DealVorschlag)
        .filter(DealVorschlag.inhaber_id == erwachsen.id, DealVorschlag.quelle_url == fund.quelle_url)
        .one()
    )
    assert erwachsenen_zeile.status == matching.STATUS_VORGESCHLAGEN

    # Keine offene Zeile mehr für das Kind auf diesem Fund - die Gruppe würde
    # in der Vorschläge-Ansicht verschwinden, sobald der Erwachsene übernommen hat.
    offene_kind_zeilen = (
        db.query(DealVorschlag)
        .filter(
            DealVorschlag.inhaber_id == kind.id,
            DealVorschlag.quelle_url == fund.quelle_url,
            DealVorschlag.status.in_(matching.STATUS_OFFEN),
        )
        .count()
    )
    assert offene_kind_zeilen == 0


def test_stehen_gebliebene_kinder_vorschlaege_werden_auch_ohne_erneuten_fund_geloescht(
    db, monkeypatch
):
    """Regressionstest für den pauschalen Vorablauf
    (_stehen_gebliebene_kinder_vorschlaege_bereinigen): ein Deal, der in den
    Quellen inzwischen gar nicht mehr gelistet ist (z.B. abgelaufen), taucht
    in keinem "Jetzt suchen"/täglichen Lauf mehr unter den frisch geladenen
    Funden auf. Trotzdem muss eine dafür noch offene Kinder-Alt-Zeile
    bereinigt werden, solange der lokale Cache (FinderFund) verrät, dass das
    Angebot kein Kinderdeal ist - ohne dass dafür ein neuer API-Aufruf nötig
    wäre."""
    erwachsen = Inhaber(name="Alice")
    kind = Inhaber(name="Kim", ist_minderjaehrig=True)
    db.add_all([erwachsen, kind])
    db.commit()

    abgelaufener_deal_url = "https://mydealz.de/laengst-abgelaufen"

    # Cache-Eintrag wie er nach einer früheren Prüfung übrig geblieben ist -
    # der Deal selbst wird in diesem Lauf nicht mehr aus der Quelle geladen.
    db.add(
        FinderFund(
            quelle="mydealz",
            quelle_url=abgelaufener_deal_url,
            rohtext_hash="irrelevant",
            ist_relevant=True,
            extraktion_json=AngebotExtraktion(
                bank_name="Bank", kontoart="Girokonto", praemie_betrag=125.0, fuer_kinder=False, bedingungen=[]
            ).model_dump_json(),
        )
    )
    alte_kind_zeile = DealVorschlag(
        inhaber_id=kind.id,
        quelle="mydealz",
        quelle_url=abgelaufener_deal_url,
        bank_name="Bank",
        kontoart="Girokonto",
        praemie_betrag=125.0,
        roh_json="{}",
        inhalt_hash="alt-hash",
        status=matching.STATUS_ZU_PRUEFEN,
    )
    db.add(alte_kind_zeile)
    db.commit()
    kind_zeile_id = alte_kind_zeile.id

    # Keine Quelle liefert in diesem Lauf irgendetwas - der abgelaufene Deal
    # kommt insbesondere nicht erneut vor.
    _patch_quellen(monkeypatch, [])
    client = FakeClient(RelevanzErgebnis(ist_relevant=True), None)

    lauf.taeglicher_lauf(db, client=client)

    db.expire_all()
    assert db.get(DealVorschlag, kind_zeile_id) is None


def test_doppelter_fund_in_einem_lauf_wird_nur_einmal_verarbeitet(db, zwei_inhaber, monkeypatch):
    """Regressionstest: finder_funde.quelle_url ist eindeutig - taucht
    dieselbe quelle_url zweimal in einem Lauf auf (z.B. weil eine Quelle
    einen Deal doppelt listet), brach der ganze Lauf bisher mit einem
    IntegrityError ab statt den doppelten Fund einfach zu überspringen."""
    fund = RohFund("mydealz", "https://mydealz.de/doppelt", "C24 125 Euro", "Neukunden erhalten 125 Euro.")
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [fund, fund])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 2  # ein Fund (dedupliziert), zwei Inhaber
    assert _letzter_lauf(db).mydealz_rauschen == 1  # der zweite, identische Fund
    assert client.aufrufe == 2  # Themen-Check + Extraktion je einmal, nicht doppelt
    assert db.query(DealVorschlag).count() == 2


def test_lauf_ist_wiederholungssicher(db, zwei_inhaber, monkeypatch):
    """Zweiter Lauf mit identischem Fund darf keine weiteren Zeilen anlegen."""
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    lauf.taeglicher_lauf(db, client=client)

    assert db.query(DealVorschlag).count() == 2
    # Zweiter Lauf: derselbe Fund ist bekannt und unverändert -> "vorhanden".
    protokoll = _letzter_lauf(db)
    assert protokoll.mydealz_neu == 0
    assert protokoll.mydealz_vorhanden == 1


def test_irrelevantes_angebot_erzeugt_keinen_vorschlag(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/versicherung", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    assert _letzter_lauf(db).mydealz_rauschen == 1  # kein Bank-Angebot -> Rauschen
    assert db.query(DealVorschlag).count() == 0


def test_benachrichtigung_nur_bei_vorgeschlagen_oder_zu_pruefen(db, zwei_inhaber, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(notify, "benachrichtigen", lambda *a, **kw: aufrufe.append((a, kw)))

    # Nur automatisch abgelehnt (Praemie zu niedrig) -> keine Benachrichtigung.
    fund = RohFund("mydealz", "https://mydealz.de/klein", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Klein-Bank", kontoart="Girokonto", praemie_betrag=5.0, bedingungen=[]),
    )
    lauf.taeglicher_lauf(db, client=client)
    assert aufrufe == []

    # Vorgeschlagen -> Benachrichtigung.
    fund2 = RohFund("mydealz", "https://mydealz.de/gross", "t", "x")
    _patch_quellen(monkeypatch, [fund2])
    client2 = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )
    lauf.taeglicher_lauf(db, client=client2)
    assert len(aufrufe) == 1


def test_benachrichtigung_konfiguration_wird_durchgereicht(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(config, "BENACHRICHTIGUNGEN_AKTIV", False)
    monkeypatch.setattr(config, "NOTIFY_GERAETE", ["mobile_app_pixel_8", "mobile_app_iphone_anna"])
    aufrufe = []
    monkeypatch.setattr(notify, "benachrichtigen", lambda *a, **kw: aufrufe.append((a, kw)))

    fund = RohFund("mydealz", "https://mydealz.de/gross", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )
    lauf.taeglicher_lauf(db, client=client)

    assert len(aufrufe) == 1
    _, kwargs = aufrufe[0]
    assert kwargs["aktiv"] is False
    assert kwargs["geraete"] == ["mobile_app_pixel_8", "mobile_app_iphone_anna"]


def _letzter_lauf(db) -> FinderLauf:
    return db.query(FinderLauf).order_by(FinderLauf.id.desc()).first()


def test_erfolgreicher_lauf_protokolliert_zaehlerstaende(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [
        RohFund("mydealz", "https://mydealz.de/1", "t", "x"),
        RohFund("mydealz", "https://mydealz.de/2", "t", "x"),
    ])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [
        RohFund("spartanien", "https://spartanien.de/1", "t", "x"),
    ])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [
        RohFund("dealdoktor", "https://dealdoktor.de/1", "t", "x"),
    ])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)

    protokoll = _letzter_lauf(db)
    assert protokoll is not None
    assert protokoll.erfolgreich is True
    assert protokoll.mydealz_geladen == 2
    assert protokoll.spartanien_geladen == 1
    assert protokoll.dealdoktor_geladen == 1
    assert protokoll.neu_gefunden == 4  # 4 Angebote (je eine Karte), nicht 4x2 Zeilen
    assert protokoll.mydealz_neu == 2
    assert protokoll.spartanien_neu == 1
    assert protokoll.dealdoktor_neu == 1
    assert protokoll.uebersprungen == 0
    assert protokoll.fehler is None
    assert protokoll.beendet_am is not None


def test_geladene_funde_gehen_je_quelle_lueckenlos_auf(db, zwei_inhaber, monkeypatch):
    """Kernanliegen der Tabelle: jeder geladene Fund landet je Quelle in genau
    einer Kategorie (neu / vorhanden / aktualisiert / rauschen). Die Summe der
    vier Kategorien muss wieder die Zahl der geladenen Funde ergeben - sonst
    'passt es nicht zusammen'."""
    relevant = RohFund("mydealz", "https://mydealz.de/gut", "t", "gutes Angebot")
    irrelevant = RohFund("mydealz", "https://mydealz.de/versicherung", "t", "Autoversicherung")
    doppelt = RohFund("mydealz", "https://mydealz.de/gut", "t", "gutes Angebot")  # gleiche URL wie relevant

    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [relevant, irrelevant, doppelt])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])

    class GemischteMessages:
        """relevant fuer /gut, irrelevant fuer /versicherung."""

        def parse(self, *, output_format, messages, **kwargs):
            text = messages[-1]["content"] if messages else ""
            if output_format is RelevanzErgebnis:
                ist_relevant = "Autoversicherung" not in text
                return SimpleNamespace(parsed_output=RelevanzErgebnis(ist_relevant=ist_relevant), stop_reason="end_turn")
            return SimpleNamespace(
                parsed_output=AngebotExtraktion(
                    bank_name="Gut-Bank", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]
                ),
                stop_reason="end_turn",
            )

    class GemischterClient:
        messages = GemischteMessages()

    zaehler = lauf.taeglicher_lauf(db, client=GemischterClient())

    protokoll = _letzter_lauf(db)
    geladen = protokoll.mydealz_geladen
    assert geladen == 3
    assert protokoll.mydealz_neu == 1  # nur /gut ist ein neues Bank-Angebot
    assert protokoll.mydealz_vorhanden == 0
    assert protokoll.mydealz_aktualisiert == 0
    assert protokoll.mydealz_rauschen == 2  # /versicherung (nicht relevant) + /gut (doppelt)
    summe = (
        protokoll.mydealz_neu
        + protokoll.mydealz_vorhanden
        + protokoll.mydealz_aktualisiert
        + protokoll.mydealz_rauschen
    )
    assert summe == geladen  # die vier Kategorien gehen lückenlos auf
    assert zaehler["gefunden"] == 2  # ein relevanter Fund x zwei Inhaber


def test_ohne_client_wird_trotzdem_protokolliert(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(lauf.config, "ANTHROPIC_API_KEY", None)
    lauf.taeglicher_lauf(db)

    protokoll = _letzter_lauf(db)
    assert protokoll is not None
    assert protokoll.erfolgreich is True
    assert "API-Key" in protokoll.fehler


def test_fehlgeschlagene_quelle_wird_als_fehler_protokolliert(db, zwei_inhaber, monkeypatch):
    def kaputt(*args, **kwargs):
        raise RuntimeError("HTTP 500")

    monkeypatch.setattr(lauf, "fetch_mydealz", kaputt)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    protokoll = _letzter_lauf(db)
    # Der Lauf selbst läuft trotzdem durch (die andere Quelle funktioniert) -
    # "erfolgreich", aber mit sichtbarem Fehlertext zur ausgefallenen Quelle.
    assert protokoll.erfolgreich is True
    assert protokoll.mydealz_geladen == 0
    assert "mydealz" in protokoll.fehler
    assert "HTTP 500" in protokoll.fehler


def test_mehrere_mydealz_gruppen_werden_alle_abgefragt_und_zusammengefuehrt(db, zwei_inhaber, monkeypatch):
    """config.MYDEALZ_GRUPPEN darf mehrere Gruppen enthalten (z.B. um
    "konto-kreditkarten" neben "vertraege-finanzen" mitzunehmen) - jede wird
    einzeln abgefragt, die Funde landen gemeinsam in mydealz_funde."""
    monkeypatch.setattr(config, "MYDEALZ_GRUPPEN", ["vertraege-finanzen", "konto-kreditkarten"])
    aufgerufene_gruppen = []

    def fake_fetch_mydealz(gruppe, **kw):
        aufgerufene_gruppen.append(gruppe)
        return [RohFund("mydealz", f"https://mydealz.de/{gruppe}", "t", "x")]

    monkeypatch.setattr(lauf, "fetch_mydealz", fake_fetch_mydealz)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    lauf.taeglicher_lauf(db, client=client)

    assert aufgerufene_gruppen == ["vertraege-finanzen", "konto-kreditkarten"]
    assert _letzter_lauf(db).mydealz_geladen == 2


def test_fehlgeschlagene_mydealz_gruppe_blockiert_die_andere_nicht(db, zwei_inhaber, monkeypatch):
    monkeypatch.setattr(config, "MYDEALZ_GRUPPEN", ["kaputt", "vertraege-finanzen"])

    def fake_fetch_mydealz(gruppe, **kw):
        if gruppe == "kaputt":
            raise RuntimeError("HTTP 500")
        return [RohFund("mydealz", "https://mydealz.de/gut", "t", "x")]

    monkeypatch.setattr(lauf, "fetch_mydealz", fake_fetch_mydealz)
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])
    client = FakeClient(RelevanzErgebnis(ist_relevant=False), None)

    lauf.taeglicher_lauf(db, client=client)

    protokoll = _letzter_lauf(db)
    assert protokoll.mydealz_geladen == 1
    assert "kaputt" in protokoll.fehler
    assert "HTTP 500" in protokoll.fehler


def test_extraktionsfehler_wird_gezaehlt_und_protokolliert(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/kaputt", "t", "x")
    _patch_quellen(monkeypatch, [fund])

    class KaputteMessages:
        def parse(self, *, output_format, **kwargs):
            raise RuntimeError("API-Fehler")

    class KaputterClient:
        messages = KaputteMessages()

    zaehler = lauf.taeglicher_lauf(db, client=KaputterClient())

    assert zaehler["uebersprungen"] == 1
    assert zaehler["gefunden"] == 0
    protokoll = _letzter_lauf(db)
    assert protokoll.erfolgreich is True
    assert protokoll.uebersprungen == 1
    assert "Themen-Check" in protokoll.fehler


def test_unerwarteter_fehler_wird_zurueckgerollt_und_als_fehlgeschlagen_protokolliert(db, zwei_inhaber, monkeypatch):
    """Ein Bug im Matching (o.ä.) darf weder halb gespeicherte Vorschläge
    hinterlassen noch die Seite abstürzen lassen - stattdessen: rollback,
    Lauf als fehlgeschlagen protokolliert."""
    fund = RohFund("mydealz", "https://mydealz.de/bug", "t", "x")
    _patch_quellen(monkeypatch, [fund])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )
    monkeypatch.setattr(
        matching, "bewerten", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("Programmierfehler"))
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert zaehler["gefunden"] == 0
    assert db.query(DealVorschlag).count() == 0
    protokoll = _letzter_lauf(db)
    assert protokoll.erfolgreich is False
    assert "Programmierfehler" in protokoll.fehler


# ---------------------------------------------------------------------------
# Cache: unveränderte/irrelevante Funde sollen keinen erneuten API-Aufruf
# auslösen (siehe FinderFund in models.py).
# ---------------------------------------------------------------------------


def test_unveraenderter_fund_wird_beim_zweiten_lauf_nicht_erneut_an_die_api_geschickt(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "immer derselbe Text")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    aufrufe_nach_erstem_lauf = client.aufrufe
    assert aufrufe_nach_erstem_lauf == 2  # Themen-Check + Struktur-Extraktion

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == aufrufe_nach_erstem_lauf  # keine weiteren API-Aufrufe
    assert zaehler["aus_cache"] == 1
    assert db.query(DealVorschlag).count() == 2  # unverändert - kein neuer Datensatz


def test_irrelevanter_fund_wird_nie_wieder_an_die_api_geschickt(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/versicherung", "t", "Autoversicherung wechseln")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(RelevanzErgebnis(ist_relevant=False), None)

    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 1  # nur der Themen-Check, keine Extraktion

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 1  # beim zweiten Lauf gar kein API-Aufruf mehr
    assert zaehler["aus_cache"] == 1
    assert db.query(DealVorschlag).count() == 0


def test_geaenderter_rohtext_bei_bestehendem_vorschlag_loest_keinen_neuen_api_aufruf_aus(db, zwei_inhaber, monkeypatch):
    """Existiert für eine Quelle-URL schon ein Vorschlag, gilt sie als
    endgültig geprüft: schwankender Rohtext derselben URL (z.B. Kommentar-/
    Bewertungszahlen im RSS-Feed) - selbst eine echte Änderung wie eine
    höhere Prämie - löst bewusst keinen erneuten API-Aufruf und keinen
    zweiten/geänderten Vorschlag mehr aus (Bug: mehrfach identischer
    "Deal öffnen"-Link durch schwankenden Rohtext derselben URL)."""
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    fund_v1 = RohFund("mydealz", "https://mydealz.de/c24", "t", "125 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v1])
    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 2  # Themen-Check + Extraktion, einmalig

    fund_v2 = RohFund("mydealz", "https://mydealz.de/c24", "t", "jetzt 150 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v2])
    lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 2  # kein weiterer Aufruf
    assert db.query(DealVorschlag).count() == 2  # keine dritte/vierte Zeile
    assert {v.praemie_betrag for v in db.query(DealVorschlag).all()} == {125}


def test_alle_neu_analysieren_ueberstimmt_bestehenden_vorschlag_gezielt(db, zwei_inhaber, monkeypatch):
    """ignoriere_cache=True (Button "Alle neu analysieren") ist weiterhin der
    bewusste Ausweg, um trotz eines bestehenden Vorschlags eine frische
    Prüfung zu erzwingen - der neue "bereits vorgeschlagen" Kurzschluss
    (siehe test_geaenderter_rohtext_bei_bestehendem_vorschlag_...) greift
    hier bewusst nicht."""
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    fund_v1 = RohFund("mydealz", "https://mydealz.de/c24", "t", "125 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v1])
    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 2

    fund_v2 = RohFund("mydealz", "https://mydealz.de/c24", "t", "jetzt 150 Euro Praemie")
    _patch_quellen(monkeypatch, [fund_v2])
    lauf.taeglicher_lauf(db, client=client, ignoriere_cache=True)

    assert client.aufrufe == 4


def test_kaputter_cache_eintrag_wird_neu_extrahiert_statt_den_lauf_abzubrechen(db, zwei_inhaber, monkeypatch):
    from praemien_tracker.models import FinderFund

    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "125 Euro Praemie")
    _patch_quellen(monkeypatch, [fund])
    db.add(
        FinderFund(
            quelle="mydealz",
            quelle_url=fund.quelle_url,
            rohtext_hash=lauf._rohtext_hash(fund.text),
            ist_relevant=True,
            extraktion_json="das ist kein gueltiges AngebotExtraktion-JSON",
        )
    )
    db.commit()

    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    zaehler = lauf.taeglicher_lauf(db, client=client)

    # Ein kaputter Cache-Eintrag wird wie ein Cache-Miss behandelt: kompletter
    # Themen-Check + Extraktion, statt den Lauf abzubrechen.
    assert client.aufrufe == 2
    assert zaehler["gefunden"] == 2


def test_sperrfrist_wird_trotz_cache_treffer_neu_bewertet(db, zwei_inhaber, monkeypatch):
    """Kernanliegen: das Matching muss weiterlaufen, auch wenn dank Cache
    kein API-Aufruf mehr nötig ist - sonst würde eine inzwischen erreichte
    Sperrfrist nie sichtbar."""
    from praemien_tracker.models import Bank, Deal

    alice = zwei_inhaber[0]
    santander = Bank(name="Santander")
    db.add(santander)
    db.commit()
    # Kündigung vor 11 Monaten - Sperrfrist von 12 Monaten noch nicht erreicht.
    heute = datetime.date.today().replace(day=1)
    jahr, monat = heute.year, heute.month - 11
    while monat <= 0:
        monat += 12
        jahr -= 1
    db.add(
        Deal(
            bank=santander,
            inhaber=alice,
            kontoart="Girokonto",
            gekuendigt=True,
            gekuendigt_im_monat=f"{jahr:04d}-{monat:02d}",
        )
    )
    db.commit()

    fund = RohFund("mydealz", "https://mydealz.de/santander", "t", "Santander 100 Euro")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=100.0, sperrfrist_monate=12, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    eintrag = db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == alice.id).one()
    assert eintrag.status == matching.STATUS_ABGELEHNT

    # Zeit vergeht: Kündigung liegt jetzt 13 statt 11 Monate zurück -
    # Sperrfrist erreicht. Rohtext bleibt gleich, also kein neuer API-Aufruf.
    eintrag_deal = db.query(Deal).filter(Deal.bank_id == santander.id).one()
    jahr2, monat2 = heute.year, heute.month - 13
    while monat2 <= 0:
        monat2 += 12
        jahr2 -= 1
    eintrag_deal.gekuendigt_im_monat = f"{jahr2:04d}-{monat2:02d}"
    db.commit()

    zaehler = lauf.taeglicher_lauf(db, client=client)

    assert client.aufrufe == 2  # weiterhin nur der allererste Themen-Check + Extraktion
    assert zaehler["aktualisiert"] >= 1
    assert _letzter_lauf(db).mydealz_aktualisiert == 1  # ein Angebot nachgezogen
    db.refresh(eintrag)
    assert eintrag.status == matching.STATUS_VORGESCHLAGEN
    # Immer noch nur eine Zeile je Inhaber, kein Duplikat.
    assert db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == alice.id).count() == 1


def test_status_wird_nicht_fuer_bereits_entschiedene_vorschlaege_ueberschrieben(db, zwei_inhaber, monkeypatch):
    """Ein vom Nutzer übernommener oder verworfener Vorschlag darf durch eine
    erneute Bewertung nicht wieder verändert werden."""
    fund = RohFund("mydealz", "https://mydealz.de/klein", "t", "5 Euro Praemie")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Klein-Bank", kontoart="Girokonto", praemie_betrag=5.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    eintrag = db.query(DealVorschlag).first()
    eintrag.status = matching.STATUS_VERWORFEN
    db.commit()

    lauf.taeglicher_lauf(db, client=client)

    db.refresh(eintrag)
    assert eintrag.status == matching.STATUS_VERWORFEN


# ---------------------------------------------------------------------------
# ignoriere_cache: "Alle neu analysieren"-Button - erzwingt für jeden Fund
# einen frischen API-Aufruf und aktualisiert bestehende Zeilen mit dem neuen
# Ergebnis, statt sich auf den unveränderten Inhalts-Hash zu verlassen.
# ---------------------------------------------------------------------------


def test_ignoriere_cache_ruft_api_trotz_cache_treffer_erneut_auf(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/c24", "t", "immer derselbe Text")
    _patch_quellen(monkeypatch, [fund])
    client = ZaehlenderFakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="C24", kontoart="Girokonto", praemie_betrag=125.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    assert client.aufrufe == 2  # Themen-Check + Struktur-Extraktion

    zaehler = lauf.taeglicher_lauf(db, client=client, ignoriere_cache=True)

    assert client.aufrufe == 4  # trotz unverändertem Rohtext erneut geprüft
    assert zaehler["aus_cache"] == 0
    assert db.query(DealVorschlag).count() == 2  # keine Duplikate angelegt


def test_ignoriere_cache_aktualisiert_bestehenden_vorschlag_mit_frischen_feldern(db, zwei_inhaber, monkeypatch):
    """Kernanliegen von "Alle neu analysieren": eine bestehende Karte soll
    z.B. eine neu erkannte Prämien-Aufschlüsselung bekommen, obwohl sich der
    Inhalts-Hash (Bank/Kontoart/Betrag/Sperrfrist/Bedingungen) nicht
    geändert hat und ein normaler Lauf die Zeile deshalb unangetastet
    ließe."""
    from praemien_tracker.finder.extraktion import PraemieExtraktion

    fund = RohFund("spartanien", "https://www.spartanien.de/santander", "t", "Santander 300 Euro")
    _patch_quellen(monkeypatch, [fund])
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [fund])

    ohne_split = AngebotExtraktion(bank_name="Santander", kontoart="Girokonto", praemie_betrag=300.0, bedingungen=[])
    lauf.taeglicher_lauf(db, client=FakeClient(RelevanzErgebnis(ist_relevant=True), ohne_split))
    vorher = db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == zwei_inhaber[0].id).one()
    alter_hash = vorher.inhalt_hash
    assert len(vorher.praemien) == 1
    assert vorher.praemien[0].geber is None

    mit_split = AngebotExtraktion(
        bank_name="Santander",
        kontoart="Girokonto",
        praemie_betrag=300.0,
        bedingungen=[],
        praemien=[
            PraemieExtraktion(betrag=50.0, geber="Spartanien", wofuer="für die Kontoeröffnung"),
            PraemieExtraktion(betrag=250.0, geber="Santander", wofuer="für den Kontowechselservice"),
        ],
    )
    lauf.taeglicher_lauf(db, client=FakeClient(RelevanzErgebnis(ist_relevant=True), mit_split), ignoriere_cache=True)

    db.refresh(vorher)
    assert vorher.inhalt_hash == alter_hash  # Hash unverändert - trotzdem aktualisiert
    assert db.query(DealVorschlag).filter(DealVorschlag.inhaber_id == zwei_inhaber[0].id).count() == 1
    assert len(vorher.praemien) == 2
    assert {p.geber for p in vorher.praemien} == {"Spartanien", "Santander"}


def test_ignoriere_cache_laesst_entschiedene_vorschlaege_unangetastet(db, zwei_inhaber, monkeypatch):
    fund = RohFund("mydealz", "https://mydealz.de/klein", "t", "5 Euro Praemie")
    monkeypatch.setattr(lauf, "fetch_mydealz", lambda gruppe, **kw: [fund])
    monkeypatch.setattr(lauf, "fetch_spartanien", lambda url, **kw: [])
    monkeypatch.setattr(lauf, "fetch_dealdoktor", lambda url, **kw: [])
    client = FakeClient(
        RelevanzErgebnis(ist_relevant=True),
        AngebotExtraktion(bank_name="Klein-Bank", kontoart="Girokonto", praemie_betrag=5.0, bedingungen=[]),
    )

    lauf.taeglicher_lauf(db, client=client)
    eintrag = db.query(DealVorschlag).first()
    eintrag.status = matching.STATUS_UEBERNOMMEN
    eintrag.bank_name = "Von Hand geändert"
    db.commit()

    lauf.taeglicher_lauf(db, client=client, ignoriere_cache=True)

    db.refresh(eintrag)
    assert eintrag.status == matching.STATUS_UEBERNOMMEN
    assert eintrag.bank_name == "Von Hand geändert"


# ---------------------------------------------------------------------------
# lauf_status()/lauf_im_hintergrund_starten(): Live-Anzeige "Suche läuft" im
# Vorschläge-Tab, damit ein Klick auf "Jetzt suchen"/"Alle neu analysieren"
# nicht bis zu einer Minute oder länger ohne jedes Feedback blockiert.
# ---------------------------------------------------------------------------


class _SyncThread:
    """Ersetzt threading.Thread im Test - führt die Zielfunktion sofort
    synchron im Testthread aus, statt echte Nebenläufigkeit zu erzeugen.
    Macht den Test deterministisch (kein Polling/Timing nötig), prüft aber
    trotzdem den echten Code aus _ausfuehren()/lauf_im_hintergrund_starten()."""

    def __init__(self, target, daemon=None, name=None):
        self._target = target

    def start(self):
        self._target()


def test_lauf_im_hintergrund_starten_fuehrt_lauf_aus_und_wird_wieder_frei(db, zwei_inhaber, monkeypatch):
    _patch_quellen(monkeypatch, [])
    monkeypatch.setattr(lauf, "_anthropic_client", lambda: FakeClient(RelevanzErgebnis(ist_relevant=False), None))
    monkeypatch.setattr(lauf.threading, "Thread", _SyncThread)

    gestartet = lauf.lauf_im_hintergrund_starten()

    assert gestartet is True
    # gestartet_am bleibt nach Abschluss bewusst stehen (wird nur angezeigt,
    # solange laeuft True ist) - nur das Flag muss zurückgesetzt sein.
    assert lauf.lauf_status()[0] is False
    assert db.query(FinderLauf).count() == 1


def test_lauf_im_hintergrund_starten_gibt_ignoriere_cache_weiter(db, zwei_inhaber, monkeypatch):
    aufrufe = []
    monkeypatch.setattr(
        lauf,
        "taeglicher_lauf",
        lambda db_arg, *, ignoriere_cache=False: aufrufe.append(ignoriere_cache) or {},
    )
    monkeypatch.setattr(lauf.threading, "Thread", _SyncThread)

    lauf.lauf_im_hintergrund_starten(ignoriere_cache=True)

    assert aufrufe == [True]


def test_lauf_im_hintergrund_starten_verhindert_parallelen_lauf():
    """Simuliert einen bereits aktiven Lauf über die internen Marker, statt
    eine echte Race Condition zwischen zwei Threads zu erzeugen (wäre
    flakey) - prüft nur den Schutz selbst."""
    assert lauf._lauf_beginnen() is True
    try:
        gestartet = lauf.lauf_im_hintergrund_starten()
        assert gestartet is False
    finally:
        lauf._lauf_beenden()
    assert lauf.lauf_status()[0] is False


def test_lauf_status_liefert_startzeitpunkt_waehrend_aktiv():
    vor = datetime.datetime.utcnow()
    assert lauf._lauf_beginnen() is True
    try:
        laeuft, gestartet_am = lauf.lauf_status()
        assert laeuft is True
        assert gestartet_am >= vor
    finally:
        lauf._lauf_beenden()
    assert lauf.lauf_status()[0] is False


def test_geplanter_lauf_uebersprungen_wenn_bereits_aktiv(monkeypatch):
    aufrufe = []
    monkeypatch.setattr(lauf, "taeglicher_lauf", lambda *a, **kw: aufrufe.append(1))
    assert lauf._lauf_beginnen() is True
    try:
        lauf.geplanter_lauf()
    finally:
        lauf._lauf_beenden()
    assert aufrufe == []


def test_geplanter_lauf_markiert_sich_und_wird_wieder_frei(db, zwei_inhaber, monkeypatch):
    _patch_quellen(monkeypatch, [])
    monkeypatch.setattr(lauf, "_anthropic_client", lambda: FakeClient(RelevanzErgebnis(ist_relevant=False), None))

    lauf.geplanter_lauf()

    assert lauf.lauf_status()[0] is False
    assert db.query(FinderLauf).count() == 1
