
## Setup & Installation

**Voraussetzungen:**

* Python 3.8+
* pip (Python package installer)
* Optional: PostgreSQL-Server (falls nicht SQLite verwendet wird)

**Schritte:**

1.  **Repository klonen:**
    ```bash
    git clone <repository-url>
    cd backend # In den Backend-Ordner wechseln
    ```
2.  **Virtuelle Umgebung erstellen (Empfohlen):**
    ```bash
    python -m venv venv
    source venv/bin/activate  # Linux/macOS
    # oder
    .\venv\Scripts\activate # Windows
    ```
3.  **Abhängigkeiten installieren:**
    ```bash
    pip install -r requirements.txt
    ```
    *(Hinweis: `requirements.txt` enthält `aiosqlite`. Wenn du PostgreSQL verwendest, musst du ggf. `psycopg2-binary` oder besser `asyncpg` installieren: `pip install asyncpg` und es zur `requirements.txt` hinzufügen).*
4.  **Umgebungsvariablen konfigurieren:**
    * Erstelle eine Datei namens `.env` im `backend`-Verzeichnis.
    * Füge die Datenbank-URL hinzu.
        * **Für SQLite (Standard):**
            ```dotenv
            DATABASE_URL=sqlite+aiosqlite:///./survey_app.db
            ```
        * **Für PostgreSQL (Beispiel):**
            ```dotenv
            DATABASE_URL=postgresql+asyncpg://DEIN_BENUTZER:DEIN_PASSWORT@localhost:5432/DEINE_DB
            ```
            (Ersetze die Platzhalter entsprechend deiner PostgreSQL-Konfiguration).
5.  **Datenbank initialisieren (Tabellen erstellen):**
    * Beim allerersten Start oder nach Änderungen an den `models.py` müssen die Datenbanktabellen erstellt werden.
    * **Für die Entwicklung:** Du kannst die Funktion `create_db_and_tables` in `database.py` verwenden. Eine Möglichkeit ist, sie einmalig manuell auszuführen oder die entsprechende Zeile im `lifespan`-Manager in `main.py` kurzzeitig einzukommentieren und den Server zu starten.
        ```python
        # In main.py, innerhalb von lifespan, vor yield:
        # await create_db_and_tables()
        ```
    * **WICHTIG:** Für spätere Änderungen an der Datenbankstruktur in einer Produktionsumgebung sollte ein Migrationstool wie **Alembic** verwendet werden!

## Anwendung starten (Entwicklung)

Führe im Terminal (im `backend`-Ordner, mit aktivierter virtueller Umgebung) folgenden Befehl aus:

```bash
uvicorn app.main:app --reload