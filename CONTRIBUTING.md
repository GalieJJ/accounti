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

### 🏦 Bank-Formate
Jede Bank hat ein eigenes CSV-Format. Wenn du einen Importer für deine Bank schreibst, hilft das allen. Bitte anonymisierte Beispieldaten mitliefern.

### 📊 Fachliche Validierung
Buchhalter und Steuerberater: Sind die Kontierungsregeln korrekt? Stimmt die BWA-Zuordnung? Fehlen Steuerschlüssel? Issues und PRs willkommen.

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
