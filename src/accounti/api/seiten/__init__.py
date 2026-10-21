"""HTML-Seiten der Oberfläche — jedes Modul mit ``router`` wird eingehängt.

Ein Modul bringt ``router = APIRouter()`` und optional ``NAVIGATION`` mit; Seiten
holen den Benutzer mit ``Depends(erfordert(Recht.X))``, die Daten mit
``Depends(gesellschaft_db)`` und rendern mit ``seite(request, "vorlage.html", …)``.
"""
