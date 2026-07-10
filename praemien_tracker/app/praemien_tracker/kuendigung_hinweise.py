"""Recherchierte Kündigungsanleitungen je Bank + Kontoart.

Wird bei jedem Start automatisch auf Deals angewendet, die noch nicht
gekündigt sind und noch keine eigene Kündigung-Anweisung tragen (siehe
backfill_kuendigung_hinweise). Bereits gesetzte oder vom Nutzer bearbeitete
Werte werden nie überschrieben - der Nutzer bleibt jederzeit Quelle der
Wahrheit, das hier ist nur ein Vorschlag für den Start.

Quellen siehe jeweilige Bank-URL.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from .models import Deal

KUENDIGUNG_HINWEISE: dict[tuple[str, str], tuple[str, str]] = {
    ("Bfor", "Kreditkarte"): (
        "Kündigung direkt in der BforBank-App möglich (Kontoverwaltung). "
        "Dort ggf. ein PDF-Kündigungsformular herunterladen, ausfüllen und "
        "per E-Mail zurücksenden. Bearbeitungszeit bis zu 3 Monate; "
        "Zielkonto für das Restguthaben angeben.",
        "https://www.bforbank.com/de/bankkonto/konto-kuendigen",
    ),
    ("Ferratum", "Kreditkarte"): (
        "Kein Online-Kündigungsformular im Kundenportal - Kündigung "
        "formlos per E-Mail an info@ferratumbank.com, per Fax oder Post an "
        "Ferratum Bank p.l.c. (Malta).",
        "https://www.ferratum.de/kontakt",
    ),
    ("Quirion", "Depot"): (
        "Online im Kundenportal (banking.quirion.de) unter Einstellungen "
        "→ Mehr → 'Geschäftsbeziehung beenden' kündbar. Alternativ reicht "
        "ein formloses, unterschriebenes Kündigungsschreiben per Post - "
        "kein spezielles Formular nötig. Hinweis: Beträge aus den letzten "
        "8 Wochen per Lastschrift werden erst nach Ablauf dieser Frist "
        "ausgezahlt.",
        "https://kundenforum.quirion.de/hc/de/articles/27524400252317-Wie-kann-ich-mein-quirion-Konto-k%C3%BCndigen",
    ),
    ("Traders Place", "Depot"): (
        "Kein Online-Weg - im Kundenbereich unter Service → Formulare → "
        "Formularcenter das Formular 'Depot-/Kontoschließung' (Baader "
        "Bank) herunterladen, ausfüllen, unterschreiben und per Post "
        "einsenden. Rückmeldung meist nach 5-10 Werktagen.",
        "https://tradersplace.de/service/service-tools/formularcenter",
    ),
    ("BBBank", "Girokonto"): (
        "Kein Online-Kündigungsweg - schriftliche Kündigung per Brief, "
        "Fax oder Einschreiben an BBBank eG, 'Kundenbetreuung', "
        "Herrenstraße 2-10, 76133 Karlsruhe. Kontonummer, gewünschtes "
        "Kündigungsdatum und Bitte um schriftliche Bestätigung angeben.",
        "https://www.bbbank.de/services/formulare.html",
    ),
    ("DB Max blue", "Depot"): (
        "Voraussetzung: Depot muss leer sein (keine Wertpapiere, kein "
        "Saldo auf dem Verrechnungskonto). Dann formlose schriftliche "
        "Kündigung an Deutsche Bank AG / maxblue Kundenservice, 04024 "
        "Leipzig senden.",
        "https://www.maxblue.de/service-kontakt/informationen/formulare.html",
    ),
    ("Comdirect", "Depot"): (
        "Depot muss vorher leer sein (Wertpapiere verkauft oder "
        "übertragen). Ist es leer, Kündigung online im Persönlichen "
        "Bereich unter Verwaltung → Meine Daten möglich, sonst "
        "schriftlich per Post. Keine Kündigungsfrist.",
        "https://www.comdirect.de/faq/kuendigung",
    ),
    ("1822direkt", "Depot"): (
        "Kein Online-Formular - formloses Kündigungsschreiben per Fax, "
        "Brief oder Einschreiben an Gesellschaft der Frankfurter "
        "Sparkasse mbH, Borsigallee 19, 60388 Frankfurt. Keine "
        "Kündigungsfrist; Eingangsbestätigung erbitten.",
        "https://www.1822direkt.de/service/formulare/",
    ),
    ("C24 Bank", "Girokonto"): (
        "Einfach in der C24-App: Profil-Symbol oben links → 'C24 "
        "Girokonto kündigen' (bzw. Verwalten-Zahnrad → 'C24 Girokonto "
        "schließen'). Nur möglich ohne negativen Saldo - bei Guthaben "
        "IBAN für die Auszahlung angeben.",
        "https://hilfe.c24.de/hc/de/articles/360011420560-Wie-schlie%C3%9Fe-ich-mein-Konto",
    ),
    ("S Broker", "Depot"): (
        "Formular 'Auftrag zur Depot-/Kontolöschung' herunterladen, "
        "ausfüllen, unterschreiben, einscannen/fotografieren und per "
        "E-Mail einsenden.",
        "https://www.sbroker.de/sites/default/files/2025-07/Auftrag_Depot-Kontoloeschung.pdf",
    ),
}


def backfill_kuendigung_hinweise(db: Session) -> int:
    deals = (
        db.query(Deal)
        .options(joinedload(Deal.bank))
        .filter(Deal.gekuendigt.is_(False), Deal.kuendigung_hinweis.is_(None))
        .all()
    )
    anzahl = 0
    for deal in deals:
        eintrag = KUENDIGUNG_HINWEISE.get((deal.bank.name, deal.kontoart))
        if eintrag:
            deal.kuendigung_hinweis, deal.kuendigung_hinweis_url = eintrag
            anzahl += 1
    if anzahl:
        db.commit()
    return anzahl
