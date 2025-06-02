# alembic/env.py
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

# NEU: Importiere create_engine für die Online-Migration, wenn DATABASE_URL direkt verwendet wird
from sqlalchemy import create_engine

from alembic import context

# Importiere os und sys für Pfadmanipulation und dotenv für .env-Handling
import os
import sys
from dotenv import load_dotenv

# Füge das Projekt-Root-Verzeichnis zum Python-Pfad hinzu,
# damit Module wie 'app.models' und 'app.database' gefunden werden.
# Das 'alembic'-Verzeichnis ist eine Ebene unter dem Projekt-Root.
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Lade Umgebungsvariablen aus der .env-Datei im Projekt-Root
# Dies stellt sicher, dass DATABASE_URL verfügbar ist.
dotenv_path = os.path.join(project_root, ".env")
if os.path.exists(dotenv_path):
    load_dotenv(dotenv_path)
    print(f"DEBUG [alembic/env.py]: .env file loaded from {dotenv_path}")
else:
    print(f"WARNUNG [alembic/env.py]: .env file not found at {dotenv_path}")


# Importiere deine SQLAlchemy Base und die DATABASE_URL aus deiner Anwendung
# Stelle sicher, dass diese Imports nach der sys.path-Anpassung erfolgen.
try:
    from app.models import Base  # Deine SQLAlchemy Base-Klasse
    from app.database import DATABASE_URL  # Deine konfigurierte DATABASE_URL

    print(f"DEBUG [alembic/env.py]: Imported Base from app.models and DATABASE_URL.")
    print(f"DEBUG [alembic/env.py]: DATABASE_URL for Alembic: {DATABASE_URL}")
except ImportError as e:
    print(
        f"FEHLER [alembic/env.py]: Konnte app.models.Base oder app.database.DATABASE_URL nicht importieren: {e}"
    )
    print(f"Aktueller sys.path: {sys.path}")
    # Beende hier, da Alembic ohne diese nicht funktionieren kann
    raise


# Dies ist das Alembic Config-Objekt, das Zugriff auf die
# Werte in der .ini-Datei ermöglicht.
config = context.config

# Interpretiere die config-Datei für Python-Logging.
# Diese Zeile geht davon aus, dass deine App bereits Logging konfiguriert hat.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Setze target_metadata auf deine Base.metadata aus app.models
# target_metadata = None # Alte Zeile auskommentieren oder löschen
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    # NEU: Verwende die DATABASE_URL aus deiner app.database
    # Stelle sicher, dass sie für synchrone Operationen geeignet ist (kein +asyncpg Suffix)
    # Alembic arbeitet typischerweise synchron für Schema-Operationen.
    if DATABASE_URL is None:
        raise ValueError("DATABASE_URL ist nicht gesetzt. Bitte in .env konfigurieren.")

    offline_url = DATABASE_URL
    if "+asyncpg" in offline_url:
        offline_url = offline_url.replace(
            "+asyncpg", ""
        )  # z.B. postgresql://user:pass@host/db
    elif (
        "+aiosqlite" in offline_url
    ):  # Falls du jemals zu SQLite zurückkehrst für offline
        offline_url = offline_url.replace("+aiosqlite", "")  # z.B. sqlite:///./file.db

    print(f"DEBUG [alembic/env.py run_migrations_offline]: Using URL: {offline_url}")
    context.configure(
        url=offline_url,  # Verwende die dynamisch geladene und angepasste URL
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # NEU: Wichtig für PostgreSQL, um Typen wie Boolean korrekt zu behandeln
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Erstelle die Engine direkt mit der DATABASE_URL aus deiner app.database
    # Die ursprüngliche config.get_section(config.config_ini_section) Logik wird nicht benötigt,
    # wenn wir die URL direkt setzen.
    if DATABASE_URL is None:
        raise ValueError("DATABASE_URL ist nicht gesetzt. Bitte in .env konfigurieren.")

    # Alembic benötigt eine synchrone Engine für Migrationen.
    online_url = DATABASE_URL
    if "+asyncpg" in online_url:
        online_url = online_url.replace("+asyncpg", "")
    elif "+aiosqlite" in online_url:
        online_url = online_url.replace("+aiosqlite", "")

    print(
        f"DEBUG [alembic/env.py run_migrations_online]: Connecting with URL: {online_url}"
    )
    # Verwende create_engine für die synchrone Engine, die Alembic hier benötigt
    connectable = create_engine(online_url)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # NEU: Wichtig für PostgreSQL
            compare_type=True,
            # Optional: Wenn du Schemas in PostgreSQL verwendest (z.B. nicht 'public')
            # include_schemas=True,
            # version_table_schema='my_schema_for_alembic_version_table'
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    print("DEBUG [alembic/env.py]: Running migrations in offline mode.")
    run_migrations_offline()
else:
    print("DEBUG [alembic/env.py]: Running migrations in online mode.")
    run_migrations_online()
