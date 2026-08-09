# Arbeitsanweisungen für dieses Repository

## Branch: nur der Default-Branch

Es wird **ausschließlich auf dem Default-Branch** gearbeitet und dorthin
gepusht – aktuell `claude/praemien-tracker-addon-5mg0hp`. Ein eigener
Feature-/Arbeitsbranch wird **nur angelegt, wenn der Nutzer das in der
jeweiligen Anfrage ausdrücklich verlangt**; ohne diese ausdrückliche Ansage
landet jede Änderung direkt auf dem Default-Branch.

**Grund:** Der Home-Assistant-Supervisor klont dieses Add-on-Repository
einmal beim Hinzufügen und holt bei „Store neu laden" immer *genau den
Branch, den er damals ausgecheckt hat*. Ein zweiter, paralleler Branch würde
dort nie ankommen, solange ihn niemand von Hand zusammenführt. Der
Default-Branch ist deshalb der einzige Ort, an dem eine Änderung für Home
Assistant überhaupt sichtbar wird.

## Version und Changelog

Home Assistant erkennt ein Update ausschließlich an der Versionsnummer im
Manifest. **Jede** Änderung, die auf den Default-Branch gepusht wird – egal
wie klein – braucht deshalb:

1. `praemien_tracker/config.yaml`: `version` erhöhen.
2. `praemien_tracker/CHANGELOG.md`: Eintrag ganz oben, in derselben Sprache
   und Ausführlichkeit wie die bestehenden – was sich ändert, und *warum*.
