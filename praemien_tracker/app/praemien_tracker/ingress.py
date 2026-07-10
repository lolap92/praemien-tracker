"""Hilfsfunktionen für den Betrieb hinter Home-Assistant-Ingress.

Ingress reicht Requests unter einem wechselnden Pfad-Präfix
(X-Ingress-Path) durch. HTML-Inhalte lösen relative Links über das
<base>-Tag in base.html gegen dieses Präfix auf. Redirects (Location-Header)
werden vom Browser jedoch nicht gegen <base> aufgelöst, sondern absolut -
deshalb wird das Präfix hier für Redirects manuell vorangestellt.
"""

from fastapi import Request
from fastapi.responses import RedirectResponse


def redirect(request: Request, path: str, status_code: int = 303) -> RedirectResponse:
    prefix = request.headers.get("X-Ingress-Path", "")
    if not path.startswith("/"):
        path = "/" + path
    return RedirectResponse(url=f"{prefix}{path}", status_code=status_code)
