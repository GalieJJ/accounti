# Mitmachen bei accounti

Danke, dass du mitmachen möchtest! Hier steht, wie du am besten beitragen kannst.

## Erste Schritte

1. Fork das Repository
2. Clone deinen Fork: `git clone https://github.com/DEIN-USER/accounti.git`
3. Erstelle einen Branch: `git checkout -b feature/mein-feature`
4. Installiere die Entwicklungsumgebung:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pre-commit install
```

## Development Setup

```bash
# Tests ausführen
pytest

# Linting
ruff check src/ tests/
ruff format src/ tests/

# Type-Checking
mypy src/
```

## Pull Requests

- Ein PR pro Feature/Fix
- Tests schreiben für neue Funktionalität
- Bestehende Tests dürfen nicht brechen
- Beschreibe klar, was dein PR macht und warum

## Wo Hilfe gebraucht wird

Was gebaut wird und in welcher Reihenfolge, steht im [Bauplan](docs/bauplan.md). Jeder Baustein hat
ein Spec unter [`docs/specs/`](docs/specs/) — wer an einem größeren Thema arbeiten will, fängt am
besten dort an und meldet sich vorher per Issue.

### 🏦 Bank-Formate
Jede Bank hat ein eigenes CSV-Format. Wenn du einen Importer für deine Bank schreibst, hilft das allen. Bitte anonymisierte Beispieldaten mitliefern.

Dasselbe gilt für Live-Zugänge: Wer eine Bank per FinTS anbindet und die Eigenheiten kennt, spart allen anderen die Fehlersuche.

### 🧾 E-Rechnung
XRechnung und ZUGFeRD haben Profile und Eigenheiten, die man nur an echten Dateien lernt. Anonymisierte Beispiele für die Format-Fixtures sind besonders wertvoll — je ungewöhnlicher, desto besser.

### 📊 Fachliche Validierung
Buchhalter und Steuerberater: Sind die Kontierungsregeln korrekt? Stimmt die BWA-Zuordnung? Fehlen Steuerschlüssel? Und, für die geplanten Prüfregeln: Welcher Befund gehört in eine ordentliche Vollständigkeitsprüfung, und welcher erzeugt nur Rauschen? Fehlalarme sind hier so schädlich wie übersehene Fehler.

### 🤖 KI-Prompts
Die Qualität der automatischen Kontierung steht und fällt mit den Prompts. Wer Erfahrung mit LLM-Prompt-Engineering hat, kann hier viel bewirken.

### 📝 Dokumentation
Tutorials, Beispiele, Übersetzungen — alles willkommen.

## Code Style

- Python: Ruff (Formatter + Linter), Zielversion Python 3.11+
- Type Hints überall
- Docstrings auf Deutsch (weil die Fachbegriffe deutsch sind)
- Variablennamen: Fachbegriffe deutsch (`buchungssatz`, `steuerschluessel`), Infrastruktur englisch (`database`, `config`)

## Commit Messages

Format: `typ: kurze beschreibung`

Typen:
- `feat:` Neues Feature
- `fix:` Bugfix
- `docs:` Dokumentation
- `test:` Tests
- `refactor:` Code-Umbau ohne Funktionsänderung
- `config:` Konfiguration, CI, Build

## Fragen?

Öffne ein Issue mit dem Label `question` oder starte eine Discussion.
