"""KI-Deal-Finder: täglicher Hintergrund-Lauf, der mydealz und spartanien nach
neuen Konto-/Depotwechsel-Prämien durchsucht (Erweiterung zum Grundkonzept).

Die Module hier trennen bewusst drei Verantwortlichkeiten:
- quellen.py: Rohtext von den Quellen holen (kein Fachwissen).
- extraktion.py: Rohtext über die Anthropic-API in strukturierte Felder
  übersetzen (die KI *versteht* Text, sie *entscheidet* nichts).
- matching.py: deterministische Prüfung der strukturierten Felder gegen die
  Kriterien und bestehende Deals (normaler, nachvollziehbarer Python-Code).
lauf.py führt die drei zu einem täglichen Durchlauf zusammen.
"""
